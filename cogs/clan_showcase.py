"""
Clan Showcase Cog for UDA (United Dueling Amity) Discord Bot.
Provides interactive modal submission for clan profiles, persistent review panels,
and automated publishing matching the official Sapphire-style clan showcase embeds.
"""

from __future__ import annotations

import io
import logging
import re
import time
from typing import Optional
import urllib.request
import uuid

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from services.clan_showcase_service import (
    DEFAULT_CLAN_COLOR,
    ClanShowcaseService,
    ClanSubmission,
    build_clan_showcase_embed,
    extract_dominant_color_from_bytes,
    fetch_image_bytes,
    parse_name_and_color,
    resolve_image_url,
    validate_image_url,
)
from services.website_sync_service import WebsiteSyncService
from utils.ui import build_clan_role_panel_embed

logger = logging.getLogger("uda_bot.clan_showcase_cog")


def is_staff_user(user: discord.User | discord.Member, guild: discord.Guild) -> bool:
    """Checks whether the user has administrator or server staff privileges in the guild."""
    if not isinstance(user, discord.Member):
        member = guild.get_member(user.id)
        if not member:
            return False
    else:
        member = user

    if member.id == guild.owner_id:
        return True
    if (
        member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
        or member.guild_permissions.manage_channels
    ):
        return True

    return False


def get_submission_from_message(
    service: ClanShowcaseService, message: discord.Message
) -> Optional[ClanSubmission]:
    """Retrieves the submission associated with a staff review message."""
    sub = service.get_submission_by_message_id(message.id)
    if sub:
        return sub

    # Check footer in message embeds for fallback ID
    if message.embeds:
        for embed in message.embeds:
            if embed.footer and embed.footer.text:
                match = re.search(r"ID:\s*([a-zA-Z0-9_-]+)", embed.footer.text)
                if match:
                    return service.get_submission(match.group(1))

    # Check message content for fallback ID
    if message.content:
        match = re.search(r"Submission ID:\s*`?([a-zA-Z0-9_-]+)`?", message.content)
        if match:
            return service.get_submission(match.group(1))

    return None


class ClanCustomHexModal(discord.ui.Modal, title="Enter Custom Hex Color"):
    """Quick modal for typing a custom hex color code or color name."""

    hex_code = discord.ui.TextInput(
        label="Hex Color Code or Name",
        placeholder="e.g. #d4af37, #38bdf8, gold, crimson, cyan...",
        style=discord.TextStyle.short,
        max_length=30,
        required=True,
    )

    def __init__(self, service: ClanShowcaseService, draft: dict[str, str]):
        super().__init__()
        self.service = service
        self.draft = draft
        if draft.get("clan_color"):
            self.hex_code.default = draft.get("clan_color")

    async def on_submit(self, interaction: discord.Interaction):
        color_val = self.hex_code.value.strip()
        _, color_int, color_hex = parse_name_and_color("temp", override_color=color_val)
        self.draft["clan_color"] = color_hex
        self.draft["clan_name_color"] = f"{self.draft['clan_name']} | {color_hex}"
        if interaction.guild:
            self.service.save_draft(interaction.guild.id, interaction.user.id, self.draft)

        clan_name, color_int, _ = parse_name_and_color(self.draft["clan_name_color"])
        updated_embed = build_clan_showcase_embed(
            clan_name=clan_name,
            color_int=color_int,
            metadata_text=self.draft["metadata"],
            description_text=self.draft["description"],
            activities_motto_text=self.draft.get("activities_motto", ""),
            logo_url=self.draft["logo_url"],
        )
        updated_embed.set_footer(
            text=f"{config.organization_name} • Clan Showcase Draft Preview"
        )
        new_view = ClanDraftConfirmationView(self.service, self.draft)
        await interaction.response.edit_message(embed=updated_embed, view=new_view)


class ClanSubmissionModal(discord.ui.Modal, title="Clan Showcase Submission"):
    """
    5-field modal form for clan leaders to submit or draft their clan profile.
    Pre-fills previous inputs or drafts so users never lose their work if they close out.
    """

    def __init__(
        self,
        service: ClanShowcaseService,
        initial_data: Optional[dict[str, str]] = None,
        selected_color: Optional[str] = None,
    ):
        super().__init__()
        self.service = service
        self.initial_data = initial_data or {}
        self.selected_color = selected_color or self.initial_data.get("selected_color") or self.initial_data.get("clan_color")

        self.clan_name = discord.ui.TextInput(
            label="Clan Name",
            placeholder="Enter your clan's official name...",
            default=self.initial_data.get("clan_name", ""),
            style=discord.TextStyle.short,
            max_length=100,
            required=True,
        )
        self.metadata = discord.ui.TextInput(
            label="Clan Metadata (Region, Leaders, Status)",
            placeholder="Region: [e.g. NA/EU/ASIA] | Founded: Date | Leader: IGN | Status: Active",
            default=self.initial_data.get("metadata", ""),
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )
        self.description = discord.ui.TextInput(
            label="Clan Description & Backstory",
            placeholder="Describe your clan's history, competitive focus, philosophy, and member community...",
            default=self.initial_data.get("description", ""),
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=True,
        )
        self.activities_motto = discord.ui.TextInput(
            label="Activities & Motto (Optional)",
            placeholder="Activities: Tournaments, Scrims | Motto: Your clan motto or battle cry",
            default=self.initial_data.get("activities_motto", ""),
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False,
        )
        self.logo_url = discord.ui.TextInput(
            label="Clan Logo / Emblem (Image Link)",
            placeholder="Direct image URL (https://...) or tap 'Choose Photo from Device' below",
            default=self.initial_data.get("logo_url", ""),
            style=discord.TextStyle.short,
            max_length=500,
            required=True,
        )

        self.add_item(self.clan_name)
        self.add_item(self.metadata)
        self.add_item(self.description)
        self.add_item(self.activities_motto)
        self.add_item(self.logo_url)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message(
                "❌ This form can only be submitted within a server.", ephemeral=True
            )
            return

        # 1. Validate & Resolve Image URL (supports direct links & Discord message links)
        is_valid_url, resolved_logo_url, url_error = await resolve_image_url(
            interaction.client, self.logo_url.value
        )
        if not is_valid_url:
            await interaction.response.send_message(
                f"❌ **Invalid Logo / Emblem URL:** {url_error}\n\n"
                "**How to provide your image:**\n"
                "• **Choice 1 (Direct Device Upload):** Use `/clan-submit image:[Select Photo or GIF]` to choose directly from your phone gallery or files!\n"
                "• **Choice 2 (Image Link):** Provide a direct link (PNG, JPG, GIF) or Discord image link.",
                ephemeral=True,
            )
            return

        # 2. Determine initial color (preserve existing draft color or default to Cerberus Gold)
        color_override = self.selected_color or self.initial_data.get("clan_color") or "#d4af37"

        # 3. Parse Name & Color
        clan_name, color_int, color_hex = parse_name_and_color(
            self.clan_name.value,
            override_color=color_override
        )

        # 4. Save draft with resolved URL so user never loses their progress
        draft = {
            "clan_name": clan_name,
            "clan_color": color_hex,
            "clan_name_color": f"{clan_name} | {color_hex}",
            "metadata": self.metadata.value,
            "description": self.description.value,
            "activities_motto": self.activities_motto.value,
            "logo_url": resolved_logo_url,
            "selected_color": color_hex,
        }
        self.service.save_draft(guild.id, interaction.user.id, draft)

        preview_embed = build_clan_showcase_embed(
            clan_name=clan_name,
            color_int=color_int,
            metadata_text=self.metadata.value,
            description_text=self.description.value,
            activities_motto_text=self.activities_motto.value,
            logo_url=resolved_logo_url,
        )
        preview_embed.set_footer(
            text=f"{config.organization_name} • Clan Showcase Draft Preview"
        )

        # 5. Show ephemeral preview with interactive color dropdown and action buttons
        confirm_view = ClanDraftConfirmationView(self.service, draft)
        await interaction.response.send_message(
            content=(
                "🔍 **Clan Profile Draft Preview**\n"
                "Review how your showcase looks below!\n"
                "• 🎨 Use the **dropdown** or **Custom Hex** button below to change your theme color.\n"
                "• When you're ready, click **🚀 Confirm & Send to Staff** to submit!"
            ),
            embed=preview_embed,
            view=confirm_view,
            ephemeral=True,
        )


class ClanDraftConfirmationView(discord.ui.View):
    """
    Interactive ephemeral view allowing applicants to review their preview embed,
    instantly change their clan theme/color via an interactive dropdown or custom hex button,
    edit form details, or confirm official submission to staff.
    """

    COLOR_OPTIONS = [
        ("#d4af37", "🟡 Cerberus Gold (#D4AF37)", "Official Cerberus Gold theme"),
        ("#10b981", "🟢 Emerald Green (#10B981)", "Official UDA Emerald Green theme"),
        ("#e74c3c", "🔴 Crimson Red (#E74C3C)", "Bold Crimson Red theme"),
        ("#3498db", "🔵 Sapphire Blue (#3498DB)", "Deep Sapphire Blue theme"),
        ("#9b59b6", "🟣 Royal Purple (#9B59B6)", "Regal Royal Purple theme"),
        ("#e67e22", "🟠 Solar Orange (#E67E22)", "Vibrant Solar Orange theme"),
        ("#2c3e50", "⚫ Shadow Onyx (#2C3E50)", "Dark Slate / Onyx theme"),
        ("#ecf0f1", "⚪ Ice Silver / White (#ECF0F1)", "Clean Frost / Silver theme"),
    ]

    def __init__(self, service: ClanShowcaseService, draft: dict[str, str]):
        super().__init__(timeout=600)
        self.service = service
        self.draft = draft

        # Add theme select menu on row 0
        current_color = draft.get("clan_color", "").lower()
        select_options = []
        for val, label, desc in self.COLOR_OPTIONS:
            is_def = (val.lower() == current_color)
            select_options.append(
                discord.SelectOption(
                    label=label,
                    value=val,
                    description=desc,
                    default=is_def,
                )
            )

        self.color_select = discord.ui.Select(
            placeholder="🎨 Change Clan Color Theme...",
            min_values=1,
            max_values=1,
            options=select_options,
            row=0,
        )
        self.color_select.callback = self.color_select_callback
        self.add_item(self.color_select)

    async def color_select_callback(self, interaction: discord.Interaction):
        new_hex = self.color_select.values[0]
        self.draft["clan_color"] = new_hex
        self.draft["clan_name_color"] = f"{self.draft['clan_name']} | {new_hex}"
        if interaction.guild:
            self.service.save_draft(interaction.guild.id, interaction.user.id, self.draft)

        clan_name, color_int, _ = parse_name_and_color(self.draft["clan_name_color"])
        updated_embed = build_clan_showcase_embed(
            clan_name=clan_name,
            color_int=color_int,
            metadata_text=self.draft["metadata"],
            description_text=self.draft["description"],
            activities_motto_text=self.draft.get("activities_motto", ""),
            logo_url=self.draft["logo_url"],
        )
        updated_embed.set_footer(
            text=f"{config.organization_name} • Clan Showcase Draft Preview"
        )
        new_view = ClanDraftConfirmationView(self.service, self.draft)
        await interaction.response.edit_message(embed=updated_embed, view=new_view)

    @discord.ui.button(
        label="Confirm & Send to Staff",
        style=discord.ButtonStyle.success,
        emoji="🚀",
        custom_id="btn_confirm_clan_draft",
        row=1,
    )
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        # 1. Locate Staff Review Channel
        _, review_chan_id = self.service.get_guild_channels(guild.id)
        review_channel = None
        if review_chan_id:
            review_channel = guild.get_channel(review_chan_id)

        if not review_channel:
            for cand_name in (
                "clan-review",
                "clan-submissions",
                "staff-review",
                "mod-logs",
                "admin-chat",
            ):
                cand = discord.utils.get(guild.text_channels, name=cand_name)
                if cand:
                    review_channel = cand
                    break

        if not review_channel or not isinstance(review_channel, discord.TextChannel):
            await interaction.response.send_message(
                "⚠️ **Staff review channel is not configured on this server.**\n"
                "Please notify a server administrator to configure the review channel using `/clan-showcase-channels`.",
                ephemeral=True,
            )
            return

        clan_name, color_int, color_hex = parse_name_and_color(self.draft["clan_name_color"])
        existing_pending = self.service.get_applicant_pending_submission(guild.id, interaction.user.id)

        if existing_pending:
            # Update existing pending submission to avoid duplicate clutter
            sub = self.service.update_submission(
                sub_id=existing_pending.id,
                clan_name=clan_name,
                color_hex=color_hex,
                color_int=color_int,
                metadata_text=self.draft["metadata"],
                description_text=self.draft["description"],
                activities_motto=self.draft.get("activities_motto", ""),
                logo_url=self.draft["logo_url"],
            )
            if sub and sub.staff_message_id:
                try:
                    staff_msg = await review_channel.fetch_message(sub.staff_message_id)
                    preview_embed = sub.to_embed()
                    preview_embed.set_footer(
                        text=f"{config.organization_name} • Clan Showcase • Submission ID: {sub.id}"
                    )
                    await staff_msg.edit(
                        content=(
                            f"📋 **Clan Showcase Submission (Updated by Applicant)**\n"
                            f"• **Clan Name:** **{sub.clan_name}** ({sub.color_hex})\n"
                            f"• **Applicant:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                            f"• **Submission ID:** `{sub.id}`\n\n"
                            f"Review the updated preview below and choose an action:"
                        ),
                        embed=preview_embed,
                    )
                except Exception as exc:
                    logger.warning("Could not update staff review message: %s", exc)
        else:
            # Create fresh submission record
            sub = self.service.create_submission(
                guild_id=guild.id,
                applicant_id=interaction.user.id,
                applicant_name=str(interaction.user),
                clan_name_color_raw=self.draft["clan_name_color"],
                metadata_text=self.draft["metadata"],
                description_text=self.draft["description"],
                activities_motto=self.draft.get("activities_motto", ""),
                logo_url=self.draft["logo_url"],
            )
            preview_embed = sub.to_embed()
            preview_embed.set_footer(
                text=f"{config.organization_name} • Clan Showcase • Submission ID: {sub.id}"
            )
            review_view = ClanReviewButtonsView(self.service)
            try:
                review_msg = await review_channel.send(
                    content=(
                        f"📋 **New Clan Showcase Submission**\n"
                        f"• **Clan Name:** **{sub.clan_name}** ({sub.color_hex})\n"
                        f"• **Applicant:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                        f"• **Submission ID:** `{sub.id}`\n\n"
                        f"Review the preview below and choose an action:"
                    ),
                    embed=preview_embed,
                    view=review_view,
                )
                self.service.link_staff_message(sub.id, review_msg.id)
            except Exception as exc:
                logger.error("Failed to post clan submission to staff review channel: %s", exc)

        # Clear draft after official confirmation
        self.service.clear_draft(guild.id, interaction.user.id)

        await interaction.response.edit_message(
            content=(
                f"🎉 **Your clan profile for {sub.clan_name} has been officially submitted to staff!**\n"
                f"• **Submission ID:** `{sub.id}`\n"
                f"• Staff will review your profile shortly. You will receive a direct message once approved!\n\n"
                f"💡 *Note: Your official clan role will be generated automatically upon approval. "
                f"Extra customizations (such as gradient colors, custom icons, or special edits) will be added by moderators if needed.*"
            ),
            embed=None,
            view=None,
        )

    @discord.ui.button(
        label="Custom Hex",
        style=discord.ButtonStyle.secondary,
        emoji="🎨",
        custom_id="btn_custom_hex_draft",
        row=1,
    )
    async def custom_hex_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        modal = ClanCustomHexModal(self.service, self.draft)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Edit Info",
        style=discord.ButtonStyle.primary,
        emoji="✏️",
        custom_id="btn_edit_clan_draft",
        row=1,
    )
    async def edit_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        modal = ClanSubmissionModal(self.service, initial_data=self.draft)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Discard Draft",
        style=discord.ButtonStyle.secondary,
        emoji="🗑️",
        custom_id="btn_discard_clan_draft",
        row=1,
    )
    async def discard_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.guild:
            self.service.clear_draft(interaction.guild.id, interaction.user.id)
        await interaction.response.edit_message(
            content=(
                "🗑️ **Draft Discarded.** Nothing was sent to staff.\n"
                "You can click **📋 Submit Clan Profile** whenever you're ready to submit!"
            ),
            embed=None,
            view=None,
        )


class ClanRejectionModal(discord.ui.Modal, title="Reject Clan Submission"):
    """Modal for staff members to provide a reason when rejecting a clan profile."""

    reason_input = discord.ui.TextInput(
        label="Reason for Rejection",
        placeholder="Explain why this submission was rejected (e.g. broken logo URL, incomplete info)...",
        style=discord.TextStyle.paragraph,
        max_length=600,
        required=True,
    )

    def __init__(
        self,
        service: ClanShowcaseService,
        submission: ClanSubmission,
        staff_message: discord.Message,
    ):
        super().__init__()
        self.service = service
        self.submission = submission
        self.staff_message = staff_message

    async def on_submit(self, interaction: discord.Interaction):
        reason = self.reason_input.value.strip()

        # Update service
        self.service.reject_submission(
            sub_id=self.submission.id,
            reviewed_by_id=interaction.user.id,
            reviewed_by_name=str(interaction.user),
            reason=reason,
        )

        # Disable buttons and update review message
        try:
            await self.staff_message.edit(
                content=(
                    f"❌ **Rejected by {interaction.user.mention}** on <t:{int(time.time())}:f>\n"
                    f"• **Clan:** **{self.submission.clan_name}**\n"
                    f"• **Applicant:** <@{self.submission.applicant_id}>\n"
                    f"• **Reason:** {reason}"
                ),
                view=None,
            )
        except Exception as exc:
            logger.warning("Could not edit staff review message: %s", exc)

        # Send ephemeral confirmation
        await interaction.response.send_message(
            f"❌ Submission `{self.submission.id}` for **{self.submission.clan_name}** has been rejected.",
            ephemeral=True,
        )

        # DM the applicant
        guild = interaction.guild
        applicant = None
        if guild:
            applicant = guild.get_member(self.submission.applicant_id)
        if not applicant:
            try:
                applicant = await interaction.client.fetch_user(self.submission.applicant_id)
            except Exception:
                applicant = None

        if applicant:
            try:
                await applicant.send(
                    f"⚠️ **Clan Showcase Submission Update**\n"
                    f"Your clan profile submission for **{self.submission.clan_name}** in "
                    f"**{guild.name if guild else config.organization_name}** was **not approved**.\n\n"
                    f"**Staff Reason:**\n> {reason}\n\n"
                    f"You are welcome to resolve this issue and re-submit your profile anytime!"
                )
            except discord.Forbidden:
                logger.warning(
                    "Could not DM rejection notice to applicant %s (DMs closed)",
                    self.submission.applicant_id,
                )


class ClanEditModal(discord.ui.Modal):
    """Modal allowing admins to edit an existing clan showcase profile live."""

    def __init__(self, service: ClanShowcaseService, submission: ClanSubmission):
        super().__init__(title=f"Edit Clan: {submission.clan_name[:30]}")
        self.service = service
        self.submission = submission

        self.clan_name = discord.ui.TextInput(
            label="Clan Name",
            default=submission.clan_name,
            placeholder="Clan Name (e.g. Cerberus Elite)",
            style=discord.TextStyle.short,
            max_length=100,
            required=True,
        )
        self.clan_color = discord.ui.TextInput(
            label="Clan Color / Theme",
            default=submission.color_hex,
            placeholder="Hex code (e.g. #d4af37) or color name (e.g. gold, blue)",
            style=discord.TextStyle.short,
            max_length=50,
            required=True,
        )
        self.metadata = discord.ui.TextInput(
            label="Clan Metadata",
            default=submission.metadata_text,
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )
        self.description = discord.ui.TextInput(
            label="Description & Philosophy",
            default=submission.description_text,
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=True,
        )
        self.logo_url = discord.ui.TextInput(
            label="Logo / Emblem Direct Image URL",
            default=submission.logo_url,
            style=discord.TextStyle.short,
            max_length=500,
            required=True,
        )

        self.add_item(self.clan_name)
        self.add_item(self.clan_color)
        self.add_item(self.metadata)
        self.add_item(self.description)
        self.add_item(self.logo_url)

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Validate & Resolve Image URL
        valid, resolved_logo_url, err = await resolve_image_url(
            interaction.client, self.logo_url.value
        )
        if not valid:
            await interaction.response.send_message(
                f"❌ **Invalid Logo URL:** {err}", ephemeral=True
            )
            return

        # 2. Parse Name & Color
        new_name, new_color_int, new_color_hex = parse_name_and_color(
            self.clan_name.value,
            override_color=self.clan_color.value.strip()
        )

        # 3. Update database record
        sub = self.service.update_submission(
            sub_id=self.submission.id,
            clan_name=new_name,
            color_hex=new_color_hex,
            color_int=new_color_int,
            metadata_text=self.metadata.value,
            description_text=self.description.value,
            activities_motto=self.submission.activities_motto,
            logo_url=resolved_logo_url,
        )
        if not sub:
            await interaction.response.send_message(
                "❌ Could not update submission in database.", ephemeral=True
            )
            return

        # 4. If published, edit live message in showcase channel
        guild = interaction.guild
        edited_published = False
        showcase_chan = None
        if guild and sub.showcase_message_id:
            showcase_chan_id, _ = self.service.get_guild_channels(guild.id)
            if showcase_chan_id:
                showcase_chan = guild.get_channel(showcase_chan_id)
            if not showcase_chan:
                for name in (
                    "official-clan-list",
                    "official-clan_x_alliances-list",
                    "clan-showcase",
                    "clans",
                ):
                    cand = discord.utils.get(guild.text_channels, name=name)
                    if cand:
                        showcase_chan = cand
                        break
            if showcase_chan and isinstance(showcase_chan, discord.TextChannel):
                try:
                    target_msg = await showcase_chan.fetch_message(sub.showcase_message_id)
                    await target_msg.edit(embed=sub.to_embed())
                    edited_published = True
                except Exception as exc:
                    logger.warning("Could not edit live showcase message: %s", exc)

        # 5. If staff review message exists, update its embed as well
        if guild and sub.staff_message_id:
            _, review_chan_id = self.service.get_guild_channels(guild.id)
            review_chan = guild.get_channel(review_chan_id) if review_chan_id else None
            if review_chan and isinstance(review_chan, discord.TextChannel):
                try:
                    staff_msg = await review_chan.fetch_message(sub.staff_message_id)
                    preview_embed = sub.to_embed()
                    preview_embed.set_footer(
                        text=f"{config.organization_name} • Clan Showcase • Submission ID: {sub.id}"
                    )
                    await staff_msg.edit(embed=preview_embed)
                except Exception:
                    pass

        # If role exists and clan was renamed, update role in Discord
        if guild and sub.role_id:
            role = guild.get_role(sub.role_id)
            if role and role.name != sub.clan_name:
                try:
                    await role.edit(name=sub.clan_name[:100], reason=f"Clan renamed to {sub.clan_name}")
                    self.service.set_clan_role(sub.id, role.id, role.name)
                except Exception as r_exc:
                    logger.warning("Could not rename Discord role for clan %s: %s", sub.clan_name, r_exc)

        # Refresh live Clan Role Assignment Panel if configured
        if guild:
            cog = interaction.client.get_cog("ClanShowcase")
            if cog and hasattr(cog, "_refresh_clan_role_panel"):
                try:
                    await cog._refresh_clan_role_panel(guild)
                except Exception as panel_exc:
                    logger.debug("Could not refresh clan role panel after edit: %s", panel_exc)

        status_msg = f"✅ **Successfully updated clan profile for {sub.clan_name}!**"
        if edited_published and showcase_chan:
            status_msg += f"\nLive embed in {showcase_chan.mention} has been updated."
        elif sub.showcase_message_id:
            status_msg += "\nUpdated in database (could not reach original Discord message)."
        else:
            status_msg += "\nUpdated in database (pending staff approval to publish)."

        await interaction.response.send_message(status_msg, ephemeral=True)


class ClanReviewButtonsView(discord.ui.View):
    """
    Persistent view with Approve and Reject buttons for staff review messages.
    Survives bot restarts with custom IDs and timeout=None.
    """

    def __init__(self, service: ClanShowcaseService):
        super().__init__(timeout=None)
        self.service = service

    @discord.ui.button(
        label="Approve & Publish",
        style=discord.ButtonStyle.success,
        custom_id="btn_approve_clan",
        emoji="✅",
    )
    async def approve_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        if not is_staff_user(interaction.user, guild):
            await interaction.response.send_message(
                "❌ You do not have permission to approve clan showcase submissions.",
                ephemeral=True,
            )
            return

        sub = get_submission_from_message(self.service, interaction.message)
        if not sub:
            await interaction.response.send_message(
                "❌ Could not find submission details in database.", ephemeral=True
            )
            return

        if sub.status == "approved":
            await interaction.response.send_message(
                "⚠️ This submission has already been approved.", ephemeral=True
            )
            return
        if sub.status == "rejected":
            await interaction.response.send_message(
                "⚠️ This submission was already rejected.", ephemeral=True
            )
            return

        # Find showcase channel
        showcase_chan_id, _ = self.service.get_guild_channels(guild.id)
        showcase_channel = None
        if showcase_chan_id:
            showcase_channel = guild.get_channel(showcase_chan_id)

        # Fallback search
        if not showcase_channel:
            for cand_name in (
                "official-clan-list",
                "official-clan_x_alliances-list",
                "clan-showcase",
                "clans",
                "official-clans",
            ):
                cand = discord.utils.get(guild.text_channels, name=cand_name)
                if cand:
                    showcase_channel = cand
                    break

        if not showcase_channel or not isinstance(showcase_channel, discord.TextChannel):
            await interaction.response.send_message(
                "⚠️ **Showcase channel is not configured.**\n"
                "Please configure where clan profiles should be posted using `/clan-showcase-channels`.",
                ephemeral=True,
            )
            return

        # Post the finished embed into the showcase channel
        showcase_embed = sub.to_embed()
        try:
            showcase_msg = await showcase_channel.send(embed=showcase_embed)
        except Exception as exc:
            await interaction.response.send_message(
                f"❌ Failed to publish embed to {showcase_channel.mention}: {exc}",
                ephemeral=True,
            )
            return

        # Update submission in service
        self.service.approve_submission(
            sub_id=sub.id,
            reviewed_by_id=interaction.user.id,
            reviewed_by_name=str(interaction.user),
            showcase_message_id=showcase_msg.id,
        )

        # Automatic Clan Role Creation & Role Icon Setup
        created_role = None
        role_notice = ""
        applicant = guild.get_member(sub.applicant_id)

        if guild.me and guild.me.guild_permissions.manage_roles:
            clean_name = sub.clan_name.strip()
            suffixed_role_name = f"{clean_name} //" if not clean_name.endswith("//") else clean_name

            # Check if role with this name already exists (matching exact or with //)
            existing_role = discord.utils.find(
                lambda r: r.name.strip().lower() in (clean_name.lower(), suffixed_role_name.lower()),
                guild.roles,
            )
            role_icon_bytes = None
            if sub.logo_url:
                try:
                    data = await fetch_image_bytes(sub.logo_url)
                    if data:
                        from PIL import Image
                        im = Image.open(io.BytesIO(data)).convert("RGBA")
                        im.thumbnail((128, 128))
                        icon_buf = io.BytesIO()
                        im.save(icon_buf, format="PNG")
                        if len(icon_buf.getvalue()) < 256 * 1024:
                            role_icon_bytes = icon_buf.getvalue()
                except Exception as img_exc:
                    logger.debug("Could not fetch image for role icon: %s", img_exc)

            role_color = discord.Colour(sub.color_int) if sub.color_int else discord.Colour.default()

            if existing_role:
                created_role = existing_role
                role_notice = f"Linked existing role **{existing_role.name}**."
                # Attempt to update icon if role icons supported and missing
                if role_icon_bytes and "ROLE_ICONS" in guild.features and not existing_role.display_icon:
                    try:
                        await existing_role.edit(display_icon=role_icon_bytes)
                    except Exception as e:
                        logger.debug("Could not set existing role icon: %s", e)
            else:
                try:
                    role_kwargs = {
                        "name": suffixed_role_name[:100],
                        "colour": role_color,
                        "mentionable": True,
                        "reason": f"Automatic Clan Role created upon approval of {sub.clan_name} by {interaction.user}",
                    }
                    if role_icon_bytes and "ROLE_ICONS" in guild.features:
                        role_kwargs["display_icon"] = role_icon_bytes

                    created_role = await guild.create_role(**role_kwargs)
                    role_notice = f"Created new clan role **{created_role.name}**."
                except Exception as r_exc:
                    # Fallback without display_icon if server boost level doesn't support ROLE_ICONS
                    try:
                        created_role = await guild.create_role(
                            name=suffixed_role_name[:100],
                            colour=role_color,
                            mentionable=True,
                            reason=f"Automatic Clan Role created upon approval of {sub.clan_name} by {interaction.user}",
                        )
                        role_notice = f"Created new clan role **{created_role.name}**."
                    except Exception as fallback_exc:
                        logger.warning("Failed to automatically create clan role for %s: %s", sub.clan_name, fallback_exc)
                        role_notice = "*(Bot could not create clan role due to hierarchy or permissions)*"

            # Persist role link to submission
            if created_role:
                self.service.set_clan_role(sub.id, created_role.id, created_role.name)

            # Assign role to clan leader / applicant (and remove @Clanless)
            if created_role and applicant:
                try:
                    cog = interaction.client.get_cog("ClanShowcase")
                    if cog and hasattr(cog, "_get_clanless_role"):
                        clanless_role = cog._get_clanless_role(guild)
                        if clanless_role and clanless_role in applicant.roles:
                            try:
                                await applicant.remove_roles(
                                    clanless_role,
                                    reason=f"Clan Leader of approved clan {sub.clan_name} - removed Clanless",
                                )
                            except Exception:
                                pass

                    if created_role < guild.me.top_role:
                        await applicant.add_roles(created_role, reason=f"Clan Leader of approved clan {sub.clan_name}")
                        role_notice += f" Assigned to {applicant.mention}."
                except Exception as assign_exc:
                    logger.warning("Failed to assign clan role %s to %s: %s", created_role.name, applicant.id, assign_exc)

        # Update staff review message: disable buttons and display approver
        try:
            review_extra = f"\n• **Role:** {role_notice}" if role_notice else ""
            await interaction.message.edit(
                content=(
                    f"✅ **Approved by {interaction.user.mention}** on <t:{int(time.time())}:f>\n"
                    f"• **Clan:** **{sub.clan_name}**\n"
                    f"• **Applicant:** <@{sub.applicant_id}>\n"
                    f"• **Published in:** {showcase_channel.mention} ([Jump to Post]({showcase_msg.jump_url}))"
                    f"{review_extra}"
                ),
                view=None,
            )
        except Exception as exc:
            logger.warning("Could not edit staff review message: %s", exc)

        # Refresh live Clan Role Assignment Panel in the guild
        cog = interaction.client.get_cog("ClanShowcase")
        if cog and hasattr(cog, "_refresh_clan_role_panel"):
            try:
                await cog._refresh_clan_role_panel(guild)
            except Exception as panel_exc:
                logger.debug("Could not refresh clan role panel after approval: %s", panel_exc)

        # Optional background sync to unitedduelingamity.org
        sync_service = WebsiteSyncService()
        if sync_service.is_configured():
            try:
                await sync_service.sync_leaderboards(
                    clans=[{
                        "id": sub.id,
                        "clan_name": sub.clan_name,
                        "color_hex": sub.color_hex,
                        "metadata": sub.metadata_text,
                        "description": sub.description_text,
                        "activities_motto": sub.activities_motto,
                        "logo_url": sub.logo_url,
                        "applicant_id": str(sub.applicant_id),
                    }]
                )
            except Exception as sync_exc:
                logger.debug("Automatic website sync on clan approval failed: %s", sync_exc)

        await interaction.response.send_message(
            f"✅ **{sub.clan_name}** profile published to {showcase_channel.mention}!",
            ephemeral=True,
        )

        # DM applicant
        applicant = guild.get_member(sub.applicant_id)
        if not applicant:
            try:
                applicant = await interaction.client.fetch_user(sub.applicant_id)
            except Exception:
                applicant = None

        if applicant:
            try:
                role_info = (
                    f"\n\n🛡️ **Official Clan Role:** **@{created_role.name}** has been automatically created and assigned to you!\n"
                    f"💡 *Note: Any extra role perks (such as gradient colors, custom icons, or special edits) will be added by moderators if needed.*"
                    if created_role
                    else ""
                )
                await applicant.send(
                    f"🎉 **Congratulations!** Your clan profile submission for **{sub.clan_name}** "
                    f"has been **approved** by staff in **{guild.name}**!\n\n"
                    f"It is now live in {showcase_channel.mention}!\n"
                    f"View your showcase here: {showcase_msg.jump_url}"
                    f"{role_info}"
                )
            except discord.Forbidden:
                logger.warning(
                    "Could not DM approval notice to applicant %s (DMs closed)",
                    sub.applicant_id,
                )

    @discord.ui.button(
        label="Reject",
        style=discord.ButtonStyle.danger,
        custom_id="btn_reject_clan",
        emoji="✖️",
    )
    async def reject_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        if not is_staff_user(interaction.user, guild):
            await interaction.response.send_message(
                "❌ You do not have permission to reject clan showcase submissions.",
                ephemeral=True,
            )
            return

        sub = get_submission_from_message(self.service, interaction.message)
        if not sub:
            await interaction.response.send_message(
                "❌ Could not find submission details in database.", ephemeral=True
            )
            return

        if sub.status == "approved":
            await interaction.response.send_message(
                "⚠️ This submission has already been approved.", ephemeral=True
            )
            return
        if sub.status == "rejected":
            await interaction.response.send_message(
                "⚠️ This submission has already been rejected.", ephemeral=True
            )
            return

        # Open rejection modal
        modal = ClanRejectionModal(
            service=self.service,
            submission=sub,
            staff_message=interaction.message,
        )
        await interaction.response.send_modal(modal)


class ClanChoiceLauncherModalView(discord.ui.View):
    """Ephemeral launcher view offering quick modal opening from the device upload guide."""

    def __init__(self, service: ClanShowcaseService):
        super().__init__(timeout=300)
        self.service = service

    @discord.ui.button(
        label="📋 Open Form with Image Link",
        style=discord.ButtonStyle.primary,
        custom_id="btn_open_form_from_guide",
    )
    async def open_form_from_guide(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        initial_data = {}
        if interaction.guild:
            draft = self.service.get_draft(interaction.guild.id, interaction.user.id)
            if draft:
                initial_data = draft
        modal = ClanSubmissionModal(self.service, initial_data=initial_data)
        await interaction.response.send_modal(modal)


class ClanSubmissionPanelView(discord.ui.View):
    """
    Persistent view with the 'Submit Clan Profile' button and device photo upload assistance.
    Placed in public channels for clan leaders to initiate the submission modal.
    """

    def __init__(self, service: ClanShowcaseService):
        super().__init__(timeout=None)
        self.service = service

    @discord.ui.button(
        label="📋 Submit Clan Profile",
        style=discord.ButtonStyle.primary,
        custom_id="btn_submit_clan_profile",
    )
    async def submit_clan_profile_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        try:
            initial_data = {}
            if interaction.guild:
                # Restore unconfirmed draft if one is in progress
                draft = self.service.get_draft(interaction.guild.id, interaction.user.id)
                if draft:
                    initial_data = draft

            modal = ClanSubmissionModal(self.service, initial_data=initial_data)
            await interaction.response.send_modal(modal)
        except Exception as exc:
            logger.error("Failed to open clan submission modal directly: %s", exc, exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"⚠️ An error occurred while opening the form: {exc}", ephemeral=True
                )

    @discord.ui.button(
        label="📱 Choose Photo from Device",
        style=discord.ButtonStyle.secondary,
        emoji="🖼️",
        custom_id="btn_clan_mobile_upload_info",
    )
    async def mobile_upload_info_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        view = ClanChoiceLauncherModalView(self.service)
        await interaction.response.send_message(
            content=(
                "📱 **Upload Directly from your Device (Phone or PC):**\n\n"
                "If you want to choose a photo or saved GIF directly from your **Camera Roll, Gallery, or Files** without having to copy/paste any links:\n\n"
                "1️⃣ Type **/clan-submit** in chat.\n"
                "2️⃣ Select the **`image`** option — your phone's photo library will open directly!\n"
                "3️⃣ Pick your clan emblem or saved GIF.\n"
                "4️⃣ The submission form will pop up immediately with your image attached!\n\n"
                "*(Or if you already have an image link, tap **Open Form with Image Link** below!)*"
            ),
            view=view,
            ephemeral=True,
        )



class ClanRoleSelect(discord.ui.Select):
    """Dropdown menu for members to select and claim their clan role."""

    def __init__(
        self,
        service: ClanShowcaseService,
        clans: list[ClanSubmission],
        placeholder: str = "🛡️ Select your official clan role...",
        custom_id: str = "clan_role_select_dynamic",
    ):
        self.service = service
        options: list[discord.SelectOption] = []
        for s in clans[:25]:
            val = str(s.role_id) if s.role_id else f"sub:{s.id}"
            desc_parts = []
            tag = getattr(s, "tag", None)
            if tag:
                desc_parts.append(f"[{tag}]")
            desc_parts.append(f"Leader: <@{s.applicant_id}>" if s.applicant_id else s.clan_name)
            desc = " • ".join(desc_parts)
            options.append(
                discord.SelectOption(
                    label=s.clan_name[:100],
                    value=val[:100],
                    description=desc[:100],
                    emoji="🛡️",
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="No clans registered",
                    value="none",
                    description="No approved clans found yet.",
                    emoji="⚠️",
                )
            )

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            custom_id=custom_id,
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        val = self.values[0]
        if val == "none":
            await interaction.response.send_message("⚠️ No verified clans are currently available to claim.", ephemeral=True)
            return

        cog = interaction.client.get_cog("ClanShowcase")
        if not cog or not hasattr(cog, "_execute_clan_role_assignment"):
            await interaction.response.send_message("❌ Clan system cog unavailable.", ephemeral=True)
            return

        role_id: Optional[int] = None
        clan_name: Optional[str] = None

        if val.startswith("sub:"):
            sub_id = val.split(":", 1)[1]
            sub = self.service.get_submission(sub_id)
            if sub:
                clan_name = sub.clan_name
                role_id = sub.role_id
                # Fallback: match role by name
                if not role_id:
                    matched_role = discord.utils.find(
                        lambda r: r.name.strip().lower() == sub.clan_name.strip().lower(),
                        interaction.guild.roles,
                    )
                    if matched_role:
                        role_id = matched_role.id
                        self.service.set_clan_role(sub.id, matched_role.id, matched_role.name)
        else:
            try:
                role_id = int(val)
                for s in self.service.get_approved_clans(interaction.guild.id):
                    if s.role_id == role_id:
                        clan_name = s.clan_name
                        break
                if not clan_name:
                    role_obj = interaction.guild.get_role(role_id)
                    if role_obj:
                        clan_name = role_obj.name
            except ValueError:
                pass

        if not role_id:
            await interaction.response.send_message(
                f"❌ The role for **{clan_name or 'this clan'}** is not yet linked or configured. Please ask tournament staff to verify it.",
                ephemeral=True,
            )
            return

        await cog._execute_clan_role_assignment(interaction, role_id, clan_name or "Clan")


class ClanSearchModal(discord.ui.Modal, title="Search & Claim Clan Role"):
    """Interactive modal allowing duelists to type their clan name or tag to claim their role."""

    def __init__(self, service: ClanShowcaseService):
        super().__init__()
        self.service = service
        self.query_input = discord.ui.TextInput(
            label="Clan Name or Tag",
            placeholder="Type your clan name, initials, or tag...",
            min_length=1,
            max_length=100,
            required=True,
        )
        self.add_item(self.query_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        cog = interaction.client.get_cog("ClanShowcase")
        if not cog or not hasattr(cog, "_execute_clan_role_assignment"):
            await interaction.response.send_message("❌ Clan system cog unavailable.", ephemeral=True)
            return

        query = self.query_input.value.strip().lower()
        approved = self.service.get_approved_clans(interaction.guild.id)
        matches = [
            s
            for s in approved
            if query in s.clan_name.lower()
            or (getattr(s, "tag", None) and query in s.tag.lower())
            or query in s.id.lower()
        ]

        if not matches:
            await interaction.response.send_message(
                f"❌ No registered clan found matching `{self.query_input.value}`.\n"
                "• Check the spelling or tag.\n"
                "• Or use `/clan-claim` with live search suggestions.\n"
                "• If your clan isn't registered, your leader can apply via `/clan-submit`.",
                ephemeral=True,
            )
            return

        if len(matches) == 1:
            target = matches[0]
            role_id = target.role_id
            if not role_id:
                matched_role = discord.utils.find(
                    lambda r: r.name.strip().lower() == target.clan_name.strip().lower(),
                    interaction.guild.roles,
                )
                if matched_role:
                    role_id = matched_role.id
                    self.service.set_clan_role(target.id, matched_role.id, matched_role.name)

            if not role_id:
                await interaction.response.send_message(
                    f"❌ **{target.clan_name}** does not have a linked Discord role yet. Please inform staff.",
                    ephemeral=True,
                )
                return

            await cog._execute_clan_role_assignment(interaction, role_id, target.clan_name)
            return

        # Multiple matches: show search results select view
        view = ClanSearchResultView(self.service, matches[:25])
        await interaction.response.send_message(
            f"🔍 Found **{len(matches)}** clans matching `{self.query_input.value}`. Choose your clan below:",
            view=view,
            ephemeral=True,
        )


class ClanSearchResultView(discord.ui.View):
    """Ephemeral selection view for multiple search matches."""

    def __init__(self, service: ClanShowcaseService, clans: list[ClanSubmission]):
        super().__init__(timeout=180)
        self.add_item(
            ClanRoleSelect(
                service,
                clans,
                placeholder="🛡️ Select from matching clans...",
                custom_id="clan_search_result_select",
            )
        )


class ClanRoleAssignmentPanelView(discord.ui.View):
    """
    Persistent View for the Clan Role Assignment Panel.
    Allows members to claim clan roles via dropdown menus or keyword search,
    switch clans cleanly, or leave their clan to become @Clanless.
    """

    def __init__(
        self,
        service: ClanShowcaseService,
        clans: Optional[list[ClanSubmission]] = None,
    ):
        super().__init__(timeout=None)
        self.service = service

        # Populate dropdown menus (up to 4 menus of 25 options each)
        if clans:
            chunk_size = 25
            chunks = [clans[i : i + chunk_size] for i in range(0, min(len(clans), 100), chunk_size)]
            for idx, chunk in enumerate(chunks):
                if len(chunks) == 1:
                    placeholder = "🛡️ Select your official clan role..."
                else:
                    first = chunk[0].clan_name[:1].upper()
                    last = chunk[-1].clan_name[:1].upper()
                    placeholder = f"🛡️ Select Clan ({first} – {last})..."
                self.add_item(
                    ClanRoleSelect(
                        service,
                        chunk,
                        placeholder=placeholder,
                        custom_id=f"clan_role_menu_{idx}",
                    )
                )

    @discord.ui.button(
        label="Search / Type Clan",
        style=discord.ButtonStyle.primary,
        emoji="🔍",
        custom_id="btn_clan_role_search",
        row=4,
    )
    async def search_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(ClanSearchModal(self.service))

    @discord.ui.button(
        label="Leave Clan / Clanless",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="btn_clan_role_leave",
        row=4,
    )
    async def leave_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        cog = interaction.client.get_cog("ClanShowcase")
        if not cog or not hasattr(cog, "_execute_clan_leave"):
            await interaction.response.send_message("❌ Clan system cog unavailable.", ephemeral=True)
            return
        await cog._execute_clan_leave(interaction)

    @discord.ui.button(
        label="Help & Rules",
        style=discord.ButtonStyle.secondary,
        emoji="❓",
        custom_id="btn_clan_role_help",
        row=4,
    )
    async def help_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="🛡️ Clan Role System Guide",
            description=(
                "**How to Manage Your Clan Alignment:**\n\n"
                "• **1 Clan Limit:** You can only represent one clan at a time. Selecting a new clan role immediately removes your previous clan role.\n"
                "• **Clanless Rule:** Selecting any clan role automatically removes the `@Clanless` role. Clicking **Leave Clan / Clanless** removes your clan role and restores `@Clanless`.\n"
                "• **Search by Typing:** Click **`🔍 Search / Type Clan`** or use `/clan-claim <name>` with live autocomplete search!\n"
                "• **New Clans:** When a new clan is officially approved by staff, it is instantly added to this panel automatically.\n"
                "• **Missing Clan?** If your clan is not registered yet, have your clan leader apply using `/clan-submit`."
            ),
            color=0x10B981,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ClanShowcaseCog(commands.Cog, name="ClanShowcase"):
    """
    Modular Discord Cog for automated clan profile submissions, staff reviews,
    and official showcase publishing.
    """

    def __init__(self, bot: commands.Bot, service: Optional[ClanShowcaseService] = None):
        self.bot = bot
        self.service = service or ClanShowcaseService()

    async def cog_load(self) -> None:
        """Register persistent views so buttons work across bot restarts."""
        panel_view = ClanSubmissionPanelView(self.service)
        review_view = ClanReviewButtonsView(self.service)
        clan_role_view = ClanRoleAssignmentPanelView(self.service)
        self.bot.add_view(panel_view)
        self.bot.add_view(review_view)
        self.bot.add_view(clan_role_view)

        # Register views for guilds with saved panels to ensure dynamic menus work
        for g_id, g_data in getattr(self.service, "_guild_channels", {}).items():
            if g_data.get("clan_role_message_id"):
                clans = self.service.get_approved_clans(g_id)
                self.bot.add_view(ClanRoleAssignmentPanelView(self.service, clans=clans))

        logger.info("Registered persistent clan showcase views (Submit Panel, Review Buttons, Clan Role Panel).")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        """Automatically updates clan database and refreshes the panel when a linked clan role is edited in Discord."""
        if not after.guild:
            return
        approved = self.service.get_approved_clans(after.guild.id)
        matched_sub = next((s for s in approved if s.role_id == after.id), None)
        if not matched_sub:
            return

        changed = False
        if before.name != after.name:
            clean_name = after.name.rstrip("/ ").strip()
            if clean_name and clean_name != matched_sub.clan_name:
                matched_sub.clan_name = clean_name
                changed = True
            matched_sub.role_name = after.name
            changed = True

        if before.color != after.color and after.color.value != 0:
            matched_sub.color_int = after.color.value
            matched_sub.color_hex = f"#{after.color.value:06x}"
            changed = True

        if changed:
            self.service._persist()
            await self._refresh_clan_role_panel(after.guild)
            logger.info("Automatically synced clan role update for '%s' (%s)", matched_sub.clan_name, after.id)

    def _get_clanless_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        """Finds the configured @Clanless role or searches by name."""
        clanless_id = self.service.get_clanless_role_id(guild.id)
        if clanless_id:
            role = guild.get_role(clanless_id)
            if role:
                return role
        for role in guild.roles:
            if role.name.strip().lower() == "clanless":
                return role
        return None

    async def _execute_clan_role_assignment(
        self, interaction: discord.Interaction, role_id: int, clan_name: str
    ) -> None:
        """
        Assigns the selected clan role to the member while:
        1. Stripping @Clanless if present.
        2. Stripping any other approved clan roles from the member.
        3. Adding the new clan role.
        """
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        target_role = guild.get_role(role_id)
        if not target_role:
            await interaction.response.send_message(
                f"❌ The role for **{clan_name}** (`{role_id}`) was not found on this server. Please contact an admin.",
                ephemeral=True,
            )
            return

        if not guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "❌ Bot is missing the `Manage Roles` permission.", ephemeral=True
            )
            return

        if target_role >= guild.me.top_role:
            await interaction.response.send_message(
                f"❌ Cannot assign **{target_role.name}** because it is positioned higher than or equal to my highest role.",
                ephemeral=True,
            )
            return

        # Collect all approved clan role IDs in this server
        approved_clans = self.service.get_approved_clans(guild.id)
        approved_role_ids = {s.role_id for s in approved_clans if s.role_id}

        # Also get clanless role
        clanless_role = self._get_clanless_role(guild)

        roles_to_remove = []
        for r in member.roles:
            if r.id in approved_role_ids and r.id != target_role.id:
                roles_to_remove.append(r)
            if clanless_role and r.id == clanless_role.id:
                roles_to_remove.append(r)

        roles_to_add = []
        if target_role not in member.roles:
            roles_to_add.append(target_role)

        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Clan role claim - removed old/clanless roles")
            if roles_to_add:
                await member.add_roles(*roles_to_add, reason=f"Claimed clan role for {clan_name}")
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Discord permission denied: I do not have permission to manage one or more of these roles.",
                ephemeral=True,
            )
            return
        except Exception as exc:
            logger.error("Error managing clan roles for %s: %s", member.id, exc)
            await interaction.response.send_message(f"❌ Failed to update roles: {exc}", ephemeral=True)
            return

        removed_names = [f"**@{r.name}**" for r in roles_to_remove]
        removed_str = f"\n• **Removed:** {', '.join(removed_names)}" if removed_names else ""

        await interaction.response.send_message(
            f"✅ **Clan Alignment Updated!**\n"
            f"• **Assigned:** {target_role.mention}{removed_str}",
            ephemeral=True,
        )

    async def _execute_clan_leave(self, interaction: discord.Interaction) -> None:
        """
        Removes all approved clan roles from the member and assigns @Clanless.
        """
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        if not guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "❌ Bot is missing the `Manage Roles` permission.", ephemeral=True
            )
            return

        approved_clans = self.service.get_approved_clans(guild.id)
        approved_role_ids = {s.role_id for s in approved_clans if s.role_id}
        clanless_role = self._get_clanless_role(guild)

        roles_to_remove = [r for r in member.roles if r.id in approved_role_ids]
        roles_to_add = []
        if clanless_role and clanless_role not in member.roles:
            if clanless_role < guild.me.top_role:
                roles_to_add.append(clanless_role)

        if not roles_to_remove and (not clanless_role or clanless_role in member.roles):
            await interaction.response.send_message(
                "ℹ️ You do not currently have any clan roles, and you already have the `@Clanless` status.",
                ephemeral=True,
            )
            return

        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Left clan / became clanless")
            if roles_to_add:
                await member.add_roles(*roles_to_add, reason="Restored @Clanless role")
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Discord permission denied: bot cannot adjust member roles due to hierarchy.",
                ephemeral=True,
            )
            return
        except Exception as exc:
            logger.error("Error executing clan leave for %s: %s", member.id, exc)
            await interaction.response.send_message(f"❌ Failed to leave clan: {exc}", ephemeral=True)
            return

        clanless_str = f" and assigned {clanless_role.mention}" if roles_to_add else ""
        await interaction.response.send_message(
            f"✅ **Clan Left Successfully.** Removed your clan role(s){clanless_str}.",
            ephemeral=True,
        )

    async def _refresh_clan_role_panel(self, guild: discord.Guild) -> None:
        """
        Edits the posted Clan Role Assignment Panel in real-time with updated clans and options.
        """
        chan_id, msg_id = self.service.get_clan_role_panel_info(guild.id)
        if not chan_id or not msg_id:
            return

        channel = guild.get_channel(chan_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(chan_id)
            except Exception:
                return

        if not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(msg_id)
            clans = self.service.get_approved_clans(guild.id)
            embed = build_clan_role_panel_embed(clans, guild.name)
            view = ClanRoleAssignmentPanelView(self.service, clans=clans)
            await message.edit(embed=embed, view=view)
            logger.info("Successfully refreshed Clan Role Assignment Panel in guild %s.", guild.id)
        except Exception as exc:
            logger.warning("Could not refresh Clan Role Assignment Panel: %s", exc)

    # -------------------------------------------------------------------------
    # Command: /clan-submit and !clan_submit
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="clan-submit",
        description="Submit or draft your clan showcase profile (choose photo/GIF from device or paste link).",
    )
    @app_commands.describe(
        image="Select a photo or saved GIF directly from your phone gallery/camera roll or files",
        image_url="Or enter a direct image/GIF URL (https://...)",
        color="Optional color preset or hex code (or leave empty to choose on form)",
    )
    async def submit_clan_slash(
        self,
        interaction: discord.Interaction,
        image: Optional[discord.Attachment] = None,
        image_url: Optional[str] = None,
        color: Optional[str] = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.", ephemeral=True
            )
            return

        initial_data = {}
        draft = self.service.get_draft(interaction.guild.id, interaction.user.id)
        if draft:
            initial_data = dict(draft)
        else:
            prev = self.service.get_applicant_submission(interaction.guild.id, interaction.user.id)
            if prev:
                initial_data = {
                    "clan_name_color": f"{prev.clan_name} | {prev.color_hex}",
                    "metadata": prev.metadata_text,
                    "description": prev.description_text,
                    "activities_motto": prev.activities_motto,
                    "logo_url": prev.logo_url,
                }

        # Check if user uploaded a photo/GIF directly from their device
        if image:
            content_type = image.content_type or ""
            filename = image.filename.lower()
            valid_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif")
            if not (content_type.startswith("image/") or any(filename.endswith(ext) for ext in valid_exts)):
                await interaction.response.send_message(
                    f"❌ The file `{image.filename}` is not a supported image or GIF format. "
                    "Please upload a PNG, JPG, WEBP, or GIF file.",
                    ephemeral=True,
                )
                return
            initial_data["logo_url"] = image.url
        elif image_url:
            valid, resolved, err = await resolve_image_url(interaction.client, image_url)
            if not valid:
                await interaction.response.send_message(
                    f"❌ **Invalid Image URL:** {err}", ephemeral=True
                )
                return
            initial_data["logo_url"] = resolved

        modal = ClanSubmissionModal(self.service, initial_data=initial_data, selected_color=color)
        await interaction.response.send_modal(modal)

    @commands.command(name="clan_submit")
    async def submit_clan_prefix(
        self, ctx: commands.Context, image_url: Optional[str] = None
    ):
        """Prefix fallback command (!clan_submit)."""
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a server.")
            return

        msg = (
            "ℹ️ Discord modals must be opened via interactive slash commands or buttons.\n"
            "Please use the slash command: **/clan-submit**\n"
            "• **To select a photo/GIF from your phone:** Use `/clan-submit image:[Select Photo]`!\n"
            "• **To use a link:** Use `/clan-submit` or click **📋 Submit Clan Profile** on the registration panel."
        )
        await ctx.send(msg)

    # -------------------------------------------------------------------------
    # Command: /post-clan-submission-panel and !post_clan_submission_panel
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="post-clan-submission-panel",
        description="Admin: Drop the interactive Clan Profile Submission panel with persistent buttons.",
    )
    @app_commands.describe(
        channel="Channel to post the submission panel in (defaults to current channel)"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def post_clan_submission_panel_slash(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        if not is_staff_user(interaction.user, interaction.guild):
            await interaction.response.send_message(
                "❌ You must be an administrator or tournament staff to post this panel.",
                ephemeral=True,
            )
            return

        target_chan = channel or interaction.channel
        if not isinstance(target_chan, discord.TextChannel):
            await interaction.response.send_message("❌ Target must be a text channel.", ephemeral=True)
            return

        panel_embed = discord.Embed(
            title="🏛️ Official Clan Profile Showcase Submissions",
            description=(
                f"Welcome to the official **{config.organization_name}** Clan Showcase submission system!\n\n"
                "Are you a clan leader looking to represent your roster in our server's official showcase? "
                "Choose your preferred method below to submit your clan's profile for staff review:\n\n"
                "**How to Provide Your Clan Logo / GIF (Choose One):**\n"
                "• **Choice 1 — Pick Photo/GIF from Device (Mobile & PC):**\n"
                "  Type `/clan-submit` and select **`image`** to choose directly from your phone's Camera Roll / Gallery or files!\n"
                "• **Choice 2 — Paste Image Link in Form:**\n"
                "  Click **📋 Submit Clan Profile** below to open the form and paste any direct image or GIF link.\n\n"
                "**Form Guidelines & Tips:**\n"
                "• **Clan Name & Info:** Enter your official clan name (e.g. `Cerberus Elite`), metadata (region, leaders), description, and motto.\n"
                "• **Interactive Color & Theme:** You can choose any preset color or enter an exact custom #hex code right on your live preview card before confirming!\n"
                "• **Safe Drafting:** Decisions aren't final until you click **Confirm & Send to Staff** on the draft preview!\n"
                "• **Clan Role Creation:** Your official clan role is created automatically upon approval. Extra customizations (such as gradient colors, custom icons, or special edits) will be added by moderators if needed.\n"
                "• All submissions are reviewed by staff before being published to the public showcase.\n\n"
                "Click **📋 Submit Clan Profile** below to begin!"
            ),
            color=DEFAULT_CLAN_COLOR,
        )
        panel_embed.set_footer(
            text=f"{config.organization_name} • Clan Registration & Showcase Portal"
        )

        view = ClanSubmissionPanelView(self.service)
        await target_chan.send(embed=panel_embed, view=view)

        await interaction.response.send_message(
            f"✅ Clan submission panel successfully posted in {target_chan.mention}!",
            ephemeral=True,
        )

    @commands.command(name="post_clan_submission_panel")
    async def post_clan_submission_panel_prefix(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """Prefix command fallback (!post_clan_submission_panel)."""
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a server.")
            return

        if not is_staff_user(ctx.author, ctx.guild):
            await ctx.send("❌ You must be an administrator or tournament staff to run this command.")
            return

        target_chan = channel or ctx.channel
        if not isinstance(target_chan, discord.TextChannel):
            await ctx.send("❌ Target must be a text channel.")
            return

        panel_embed = discord.Embed(
            title="🏛️ Official Clan Profile Showcase Submissions",
            description=(
                f"Welcome to the official **{config.organization_name}** Clan Showcase submission system!\n\n"
                "Are you a clan leader looking to represent your roster in our server's official showcase? "
                "Choose your preferred method below to submit your clan's profile for staff review:\n\n"
                "**How to Provide Your Clan Logo / GIF (Choose One):**\n"
                "• **Choice 1 — Pick Photo/GIF from Device (Mobile & PC):**\n"
                "  Type `/clan-submit` and select **`image`** to choose directly from your phone's Camera Roll / Gallery or files!\n"
                "• **Choice 2 — Paste Image Link in Form:**\n"
                "  Click **📋 Submit Clan Profile** below to open the form and paste any direct image or GIF link.\n\n"
                "**Form Guidelines & Tips:**\n"
                "• **Clan Name & Info:** Enter your official clan name (e.g. `Cerberus Elite`), metadata (region, leaders), description, and motto.\n"
                "• **Interactive Color & Theme:** You can choose any preset color or enter an exact custom #hex code right on your live preview card before confirming!\n"
                "• **Safe Drafting:** Decisions aren't final until you click **Confirm & Send to Staff** on the draft preview!\n"
                "• **Clan Role Creation:** Your official clan role is created automatically upon approval. Extra customizations (such as gradient colors, custom icons, or special edits) will be added by moderators if needed.\n"
                "• All submissions are reviewed by staff before being published to the public showcase.\n\n"
                "Click **📋 Submit Clan Profile** below to begin!"
            ),
            color=DEFAULT_CLAN_COLOR,
        )
        panel_embed.set_footer(
            text=f"{config.organization_name} • Clan Registration & Showcase Portal"
        )

        view = ClanSubmissionPanelView(self.service)
        await target_chan.send(embed=panel_embed, view=view)
        await ctx.send(f"✅ Clan submission panel posted in {target_chan.mention}!")

    # -------------------------------------------------------------------------
    # Command: /clan-showcase-channels
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="clan-showcase-channels",
        description="Admin: Configure target showcase and staff review channels for this server.",
    )
    @app_commands.describe(
        showcase_channel="Public channel where approved clan embeds will be published",
        staff_review_channel="Private channel where staff review new clan submissions",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def set_clan_channels(
        self,
        interaction: discord.Interaction,
        showcase_channel: Optional[discord.TextChannel] = None,
        staff_review_channel: Optional[discord.TextChannel] = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        if not is_staff_user(interaction.user, interaction.guild):
            await interaction.response.send_message(
                "❌ You must be an administrator to configure showcase channels.",
                ephemeral=True,
            )
            return

        if not showcase_channel and not staff_review_channel:
            await interaction.response.send_message(
                "⚠️ Please provide at least one channel to update (`showcase_channel` or `staff_review_channel`).",
                ephemeral=True,
            )
            return

        self.service.set_guild_channels(
            guild_id=interaction.guild.id,
            showcase_channel_id=showcase_channel.id if showcase_channel else None,
            staff_review_channel_id=staff_review_channel.id if staff_review_channel else None,
        )

        s_id, r_id = self.service.get_guild_channels(interaction.guild.id)
        embed = discord.Embed(
            title="📁 Clan Showcase Channels Configured",
            color=DEFAULT_CLAN_COLOR,
            description="The routing for clan submissions has been updated successfully.",
        )
        embed.add_field(
            name="Public Showcase Channel",
            value=f"<#{s_id}> (`{s_id}`)" if s_id else "*(Not set - will attempt auto-detect)*",
            inline=False,
        )
        embed.add_field(
            name="Staff Review Channel",
            value=f"<#{r_id}> (`{r_id}`)" if r_id else "*(Not set - will attempt auto-detect)*",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------------------------------------------------------------------------
    # Command: /clan-showcase-view-channels
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="clan-showcase-view-channels",
        description="Admin: View current showcase and staff review channels for this server.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def view_clan_channels(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        if not is_staff_user(interaction.user, interaction.guild):
            await interaction.response.send_message(
                "❌ You must be an administrator or tournament staff to view channel settings.",
                ephemeral=True,
            )
            return

        s_id, r_id = self.service.get_guild_channels(interaction.guild.id)
        embed = discord.Embed(
            title="📁 Current Clan Showcase Channels",
            color=DEFAULT_CLAN_COLOR,
        )
        embed.add_field(
            name="Public Showcase Channel",
            value=f"<#{s_id}> (`{s_id}`)" if s_id else "*(Not configured)*",
            inline=False,
        )
        embed.add_field(
            name="Staff Review Channel",
            value=f"<#{r_id}> (`{r_id}`)" if r_id else "*(Not configured)*",
            inline=False,
        )
        embed.set_footer(
            text="Use /clan-showcase-channels to update target channels anytime."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------------------------------------------------------------------------
    # Command: /clan-showcase-edit and !clan_edit
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="clan-showcase-edit",
        description="Admin: Edit an existing clan showcase profile live in Discord.",
    )
    @app_commands.describe(
        clan="Clan name or submission ID to edit"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def edit_clan_showcase(
        self, interaction: discord.Interaction, clan: str
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        if not is_staff_user(interaction.user, interaction.guild):
            await interaction.response.send_message(
                "❌ You must be an administrator or tournament staff to edit clan profiles.",
                ephemeral=True,
            )
            return

        sub = self.service.search_submission(interaction.guild.id, clan)
        if not sub:
            await interaction.response.send_message(
                f"❌ Could not find any clan profile matching `{clan}`. "
                "Please verify the clan name or ID and try again.",
                ephemeral=True,
            )
            return

        modal = ClanEditModal(self.service, sub)
        await interaction.response.send_modal(modal)

    @edit_clan_showcase.autocomplete("clan")
    async def clan_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        if not interaction.guild:
            return []
        guild_subs = self.service.get_guild_submissions(interaction.guild.id)
        choices: list[app_commands.Choice[str]] = []
        cur_lower = current.strip().lower()
        for s in guild_subs:
            label = f"{s.clan_name} ({s.status})"
            if not cur_lower or cur_lower in s.clan_name.lower() or cur_lower in s.id.lower():
                choices.append(app_commands.Choice(name=label[:100], value=s.id))
            if len(choices) >= 25:
                break
        return choices

    @commands.command(name="clan_edit")
    async def edit_clan_prefix(self, ctx: commands.Context, *, clan: str):
        """Prefix fallback command (!clan_edit <clan_name_or_id>)."""
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a server.")
            return

        if not is_staff_user(ctx.author, ctx.guild):
            await ctx.send("❌ You must be an administrator or tournament staff to edit clan profiles.")
            return

        sub = self.service.search_submission(ctx.guild.id, clan)
        if not sub:
            await ctx.send(f"❌ Could not find any clan profile matching `{clan}`.")
            return

        await ctx.send(
            f"ℹ️ To open the interactive edit form for **{sub.clan_name}**, please use the slash command: `/clan-showcase-edit clan:{sub.clan_name}`"
        )

    # -------------------------------------------------------------------------
    # Command: /clan-showcase-preview
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="clan-showcase-preview",
        description="Preview how a clan showcase embed will look before submitting.",
    )
    @app_commands.describe(
        clan_name="Clan Name (e.g. Shadow Syndicate)",
        hex_color="Hex color code (e.g. #38bdf8)",
        logo_url="Direct image link for clan logo and emblem banner",
    )
    async def preview_showcase_embed(
        self,
        interaction: discord.Interaction,
        clan_name: str = "Example Clan",
        hex_color: str = "#38bdf8",
        logo_url: str = "https://i.imgur.com/8Q9Z5yZ.png",
    ):
        """Allows testing the Sapphire-identical embed format live."""
        _, color_int, _ = parse_name_and_color(f"{clan_name} | {hex_color}")
        demo_embed = build_clan_showcase_embed(
            clan_name=clan_name,
            color_int=color_int,
            metadata_text=(
                "Region: North America\n"
                "Founded: January 2026\n"
                "Leader: @Leader\n"
                "Co-leader: @CoLeader1, @CoLeader2\n\n"
                "Status: Active"
            ),
            description_text=(
                f"{clan_name} is a competitive community dedicated to teamwork, growth, "
                "and tournament excellence. Through structured practices, scrimmages, and ranking systems, "
                "members sharpen their mechanics and represent the clan on the battlefield."
            ),
            activities_motto_text=(
                "• Competitive Clan Wars\n"
                "• Training Sessions\n"
                "• Scrims\n"
                "• Tournaments\n\n"
                'Motto:\n"United We Conquer." ⚔️'
            ),
            logo_url=logo_url,
        )
        await interaction.response.send_message(
            content="🔍 **Clan Showcase Embed Preview (Sapphire-identical style):**",
            embed=demo_embed,
            ephemeral=True,
        )

    # -------------------------------------------------------------------------
    # Command: /post-clan-role-panel and !post_clan_role_panel
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="post-clan-role-panel",
        description="Admin: Post or move the interactive Clan Role Assignment Panel.",
    )
    @app_commands.describe(channel="Target channel to post the panel (defaults to current)")
    @app_commands.default_permissions(manage_guild=True)
    async def post_clan_role_panel_slash(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        if not is_staff_user(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ You must be an administrator or staff member.", ephemeral=True)
            return

        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message("❌ Target channel must be a text channel.", ephemeral=True)
            return

        perms = target_channel.permissions_for(interaction.guild.me)
        if not perms.send_messages or not perms.embed_links:
            await interaction.response.send_message(
                f"❌ Bot lacks `Send Messages` or `Embed Links` permissions in {target_channel.mention}.",
                ephemeral=True,
            )
            return

        clans = self.service.get_approved_clans(interaction.guild.id)
        embed = build_clan_role_panel_embed(clans, interaction.guild.name)
        view = ClanRoleAssignmentPanelView(self.service, clans=clans)

        panel_msg = await target_channel.send(embed=embed, view=view)
        self.service.set_clan_role_panel_info(interaction.guild.id, target_channel.id, panel_msg.id)

        await interaction.response.send_message(
            f"✅ **Clan Role Assignment Panel successfully posted in {target_channel.mention}!**\n"
            f"[Jump to Panel]({panel_msg.jump_url})",
            ephemeral=True,
        )

    @commands.command(name="post_clan_role_panel")
    async def post_clan_role_panel_prefix(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """Prefix fallback: !post_clan_role_panel [#channel]"""
        if not ctx.guild:
            await ctx.send("❌ Command must be used in a server.")
            return
        if not is_staff_user(ctx.author, ctx.guild):
            await ctx.send("❌ You must be an administrator or staff member.")
            return
        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            await ctx.send("❌ Target channel must be a text channel.")
            return
        clans = self.service.get_approved_clans(ctx.guild.id)
        embed = build_clan_role_panel_embed(clans, ctx.guild.name)
        view = ClanRoleAssignmentPanelView(self.service, clans=clans)
        panel_msg = await target_channel.send(embed=embed, view=view)
        self.service.set_clan_role_panel_info(ctx.guild.id, target_channel.id, panel_msg.id)
        await ctx.send(f"✅ Clan Role Assignment Panel posted in {target_channel.mention} ([Jump to Panel]({panel_msg.jump_url}))")

    # -------------------------------------------------------------------------
    # Command: /clan-claim and !clan_claim
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="clan-claim",
        description="Claim or switch to your official clan role.",
    )
    @app_commands.describe(clan="Select or type your registered clan name or tag")
    async def clan_claim_slash(self, interaction: discord.Interaction, clan: str):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        sub = self.service.get_submission(clan)
        if not sub:
            sub = self.service.search_submission(interaction.guild.id, clan)

        if not sub or sub.status != "approved":
            approved = self.service.get_approved_clans(interaction.guild.id)
            for s in approved:
                tag = getattr(s, "tag", None)
                if clan.strip().lower() in s.clan_name.lower() or (tag and clan.strip().lower() == tag.lower()):
                    sub = s
                    break

        if not sub:
            await interaction.response.send_message(
                f"❌ No approved clan matching `{clan}` was found in this server. Use `/clan-claim` with autocomplete or check the clan role panel.",
                ephemeral=True,
            )
            return

        role_id = sub.role_id
        if not role_id:
            matched_role = discord.utils.find(
                lambda r: r.name.strip().lower() == sub.clan_name.strip().lower(),
                interaction.guild.roles,
            )
            if matched_role:
                role_id = matched_role.id
                self.service.set_clan_role(sub.id, matched_role.id, matched_role.name)

        if not role_id:
            await interaction.response.send_message(
                f"❌ **{sub.clan_name}** does not have an active Discord role linked. Please ask an admin to configure it using `/clan-role-edit`.",
                ephemeral=True,
            )
            return

        await self._execute_clan_role_assignment(interaction, role_id, sub.clan_name)

    @clan_claim_slash.autocomplete("clan")
    async def clan_claim_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        if not interaction.guild:
            return []
        approved = self.service.get_approved_clans(interaction.guild.id)
        choices: list[app_commands.Choice[str]] = []
        cur = current.strip().lower()
        for s in approved:
            label = s.clan_name
            tag = getattr(s, "tag", None)
            if tag:
                label = f"[{tag}] {label}"
            if not cur or cur in s.clan_name.lower() or (tag and cur in tag.lower()):
                choices.append(app_commands.Choice(name=label[:100], value=s.id))
            if len(choices) >= 25:
                break
        return choices

    @commands.command(name="clan_claim")
    async def clan_claim_prefix(self, ctx: commands.Context, *, clan: str):
        """Prefix fallback: !clan_claim <clan_name>"""
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            await ctx.send("❌ Command must be used in a server.")
            return

        sub = self.service.get_submission(clan)
        if not sub:
            sub = self.service.search_submission(ctx.guild.id, clan)

        if not sub or sub.status != "approved":
            approved = self.service.get_approved_clans(ctx.guild.id)
            for s in approved:
                tag = getattr(s, "tag", None)
                if clan.strip().lower() in s.clan_name.lower() or (tag and clan.strip().lower() == tag.lower()):
                    sub = s
                    break

        if not sub:
            await ctx.send(f"❌ No approved clan matching `{clan}` was found.")
            return

        role_id = sub.role_id
        if not role_id:
            matched_role = discord.utils.find(
                lambda r: r.name.strip().lower() == sub.clan_name.strip().lower(),
                ctx.guild.roles,
            )
            if matched_role:
                role_id = matched_role.id
                self.service.set_clan_role(sub.id, matched_role.id, matched_role.name)

        if not role_id:
            await ctx.send(f"❌ **{sub.clan_name}** does not have a linked Discord role yet.")
            return

        target_role = ctx.guild.get_role(role_id)
        if not target_role:
            await ctx.send(f"❌ Role `{role_id}` not found on this server.")
            return

        approved_clans = self.service.get_approved_clans(ctx.guild.id)
        approved_role_ids = {s.role_id for s in approved_clans if s.role_id}
        clanless_role = self._get_clanless_role(ctx.guild)

        roles_to_remove = [
            r
            for r in ctx.author.roles
            if (r.id in approved_role_ids and r.id != target_role.id)
            or (clanless_role and r.id == clanless_role.id)
        ]
        if roles_to_remove:
            await ctx.author.remove_roles(*roles_to_remove, reason="Clan claim")
        if target_role not in ctx.author.roles:
            await ctx.author.add_roles(target_role, reason="Clan claim")

        await ctx.send(f"✅ {ctx.author.mention} claimed the **{target_role.name}** clan role!")

    # -------------------------------------------------------------------------
    # Command: /clan-leave and !clan_leave
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="clan-leave",
        description="Leave your current clan and return to @Clanless status.",
    )
    async def clan_leave_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return
        await self._execute_clan_leave(interaction)

    @commands.command(name="clan_leave")
    async def clan_leave_prefix(self, ctx: commands.Context):
        """Prefix fallback: !clan_leave"""
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            await ctx.send("❌ Command must be used in a server.")
            return
        approved_clans = self.service.get_approved_clans(ctx.guild.id)
        approved_role_ids = {s.role_id for s in approved_clans if s.role_id}
        clanless_role = self._get_clanless_role(ctx.guild)

        roles_to_remove = [r for r in ctx.author.roles if r.id in approved_role_ids]
        roles_to_add = []
        if clanless_role and clanless_role not in ctx.author.roles:
            roles_to_add.append(clanless_role)

        if not roles_to_remove and not roles_to_add:
            await ctx.send("ℹ️ You do not currently have any clan roles, and you already have @Clanless.")
            return

        if roles_to_remove:
            await ctx.author.remove_roles(*roles_to_remove, reason="Left clan")
        if roles_to_add:
            await ctx.author.add_roles(*roles_to_add, reason="Restored @Clanless")

        clanless_str = f" and assigned {clanless_role.mention}" if roles_to_add else ""
        await ctx.send(f"✅ {ctx.author.mention} left their clan{clanless_str}.")

    # -------------------------------------------------------------------------
    # Command: /clan-set-clanless-role and !set_clanless_role
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="clan-set-clanless-role",
        description="Admin: Configure the @Clanless role assigned to players without a clan.",
    )
    @app_commands.describe(role="The role to use for @Clanless members")
    @app_commands.default_permissions(manage_guild=True)
    async def set_clanless_role_slash(
        self, interaction: discord.Interaction, role: discord.Role
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        if not is_staff_user(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ You must be an administrator or staff member.", ephemeral=True)
            return

        self.service.set_clanless_role_id(interaction.guild.id, role.id)
        embed = discord.Embed(
            title="🛡️ Clanless Role Configured",
            description=(
                f"The default clanless role has been set to {role.mention} (`{role.id}`).\n\n"
                "• Members who claim a clan role will have this role automatically removed.\n"
                "• Members who leave their clan via the panel will have this role automatically restored."
            ),
            color=DEFAULT_CLAN_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="set_clanless_role")
    async def set_clanless_role_prefix(self, ctx: commands.Context, role: discord.Role):
        """Prefix fallback: !set_clanless_role <@Role>"""
        if not ctx.guild:
            await ctx.send("❌ Command must be used in a server.")
            return
        if not is_staff_user(ctx.author, ctx.guild):
            await ctx.send("❌ You must be an administrator or staff member.")
            return
        self.service.set_clanless_role_id(ctx.guild.id, role.id)
        await ctx.send(f"✅ Configured @Clanless role to {role.mention} (`{role.id}`).")

    # -------------------------------------------------------------------------
    # Command: /clan-role-edit
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="clan-role-edit",
        description="Admin: Edit, rename, or link a Discord role for an approved clan.",
    )
    @app_commands.describe(
        clan="Approved clan to update",
        new_name="New name for the clan and its Discord role",
        role="Existing Discord role to link to this clan",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def clan_role_edit_slash(
        self,
        interaction: discord.Interaction,
        clan: str,
        new_name: Optional[str] = None,
        role: Optional[discord.Role] = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        if not is_staff_user(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ You must be an administrator or staff member.", ephemeral=True)
            return

        sub = self.service.get_submission(clan)
        if not sub:
            sub = self.service.search_submission(interaction.guild.id, clan)

        if not sub:
            await interaction.response.send_message(f"❌ Clan `{clan}` not found.", ephemeral=True)
            return

        changes = []
        old_name = sub.clan_name
        if new_name and new_name.strip() and new_name.strip() != sub.clan_name:
            sub.clan_name = new_name.strip()
            changes.append(f"• Renamed clan from **{old_name}** to **{sub.clan_name}**")
            if sub.role_id:
                curr_role = interaction.guild.get_role(sub.role_id)
                if curr_role and curr_role < interaction.guild.me.top_role:
                    try:
                        await curr_role.edit(name=sub.clan_name[:100], reason="Renamed via /clan-role-edit")
                        changes.append(f"• Renamed role {curr_role.mention}")
                    except Exception as exc:
                        changes.append(f"• *(Could not rename role: {exc})*")

        if role:
            sub.role_id = role.id
            sub.role_name = role.name
            changes.append(f"• Linked Discord role {role.mention} (`{role.id}`)")
        elif sub.role_id:
            sub.role_name = sub.clan_name

        self.service._submissions[sub.id] = sub
        self.service._persist()

        # Refresh panel live
        await self._refresh_clan_role_panel(interaction.guild)

        embed = discord.Embed(
            title="🛡️ Clan Role Configuration Updated",
            color=DEFAULT_CLAN_COLOR,
            description="\n".join(changes) if changes else "No changes specified.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @clan_role_edit_slash.autocomplete("clan")
    async def clan_role_edit_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        if not interaction.guild:
            return []
        approved = self.service.get_approved_clans(interaction.guild.id)
        choices: list[app_commands.Choice[str]] = []
        cur = current.strip().lower()
        for s in approved:
            label = f"{s.clan_name} (Role: {s.role_name or 'None'})"
            tag = getattr(s, "tag", None)
            if not cur or cur in s.clan_name.lower() or (tag and cur in tag.lower()):
                choices.append(app_commands.Choice(name=label[:100], value=s.id))
            if len(choices) >= 25:
                break
        return choices

    # -------------------------------------------------------------------------
    # Command: /clan-role-panel-refresh and !refresh_clan_role_panel
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="clan-role-panel-refresh",
        description="Admin: Manually re-sync and refresh the Clan Role Assignment Panel.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def refresh_clan_role_panel_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return
        if not is_staff_user(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ You must be an administrator or staff member.", ephemeral=True)
            return

        chan_id, msg_id = self.service.get_clan_role_panel_info(interaction.guild.id)
        if not chan_id or not msg_id:
            await interaction.response.send_message(
                "⚠️ No active Clan Role Assignment Panel found for this server. Use `/post-clan-role-panel` first.",
                ephemeral=True,
            )
            return

        await self._refresh_clan_role_panel(interaction.guild)
        await interaction.response.send_message(
            f"✅ Clan Role Assignment Panel in <#{chan_id}> has been refreshed live!",
            ephemeral=True,
        )

    @commands.command(name="refresh_clan_role_panel")
    async def refresh_clan_role_panel_prefix(self, ctx: commands.Context):
        """Prefix fallback: !refresh_clan_role_panel"""
        if not ctx.guild:
            await ctx.send("❌ Command must be used in a server.")
            return
        if not is_staff_user(ctx.author, ctx.guild):
            await ctx.send("❌ You must be an administrator or staff member.")
            return
        chan_id, msg_id = self.service.get_clan_role_panel_info(ctx.guild.id)
        if not chan_id or not msg_id:
            await ctx.send("⚠️ No active Clan Role Assignment Panel found. Use !post_clan_role_panel first.")
            return
        await self._refresh_clan_role_panel(ctx.guild)
        await ctx.send(f"✅ Clan Role Assignment Panel refreshed in <#{chan_id}>.")

    # -------------------------------------------------------------------------
    # Command: /clan-delete and !clan_delete
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="clan-delete",
        description="Admin: Remove a clan from the database and Claim Role Panel (optional: delete Discord role).",
    )
    @app_commands.describe(
        clan="The clan to remove from the registry and directory panel",
        delete_discord_role="Whether to also permanently delete the Discord role from the server (default: False)",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def clan_delete_slash(
        self,
        interaction: discord.Interaction,
        clan: str,
        delete_discord_role: bool = False,
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return
        if not is_staff_user(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ You must be an administrator or staff member.", ephemeral=True)
            return

        sub = self.service.get_submission(clan)
        if not sub or sub.guild_id != interaction.guild.id:
            sub = self.service.search_submission(interaction.guild.id, clan)
        if not sub or sub.guild_id != interaction.guild.id:
            await interaction.response.send_message(f"❌ No registered clan found matching `{clan}`.", ephemeral=True)
            return

        clan_name = sub.clan_name
        role_status = "Discord role kept intact."
        if delete_discord_role and sub.role_id:
            target_role = interaction.guild.get_role(sub.role_id)
            if target_role:
                try:
                    if target_role < interaction.guild.me.top_role:
                        await target_role.delete(reason=f"Clan {clan_name} deleted by {interaction.user}")
                        role_status = f"Discord role **@{target_role.name}** was deleted from the server."
                    else:
                        role_status = f"⚠️ Could not delete Discord role **@{target_role.name}** (role is above bot in hierarchy)."
                except Exception as del_err:
                    role_status = f"⚠️ Could not delete Discord role: {del_err}"
            else:
                role_status = "Discord role was already missing from server."

        # Delete submission from service
        self.service.delete_submission(sub.id)

        # Refresh panel live
        await self._refresh_clan_role_panel(interaction.guild)

        embed = discord.Embed(
            title="🗑️ Clan Removed from Registry",
            color=0xE74C3C,
            description=(
                f"Successfully deleted **{clan_name}** from the clan registry and Claim Role directory.\n\n"
                f"• **Role Status:** {role_status}\n"
                "• **Directory Panel:** Refreshed live in real-time."
            ),
        )
        embed.set_footer(text=f"{config.organization_name} • Clan Management")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @clan_delete_slash.autocomplete("clan")
    async def clan_delete_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        if not interaction.guild:
            return []
        approved = self.service.get_approved_clans(interaction.guild.id)
        choices: list[app_commands.Choice[str]] = []
        cur = current.strip().lower()
        for s in approved:
            label = f"{s.clan_name} (Role: {s.role_name or 'None'})"
            if not cur or cur in s.clan_name.lower():
                choices.append(app_commands.Choice(name=label[:100], value=s.id))
            if len(choices) >= 25:
                break
        return choices

    @commands.command(name="clan_delete")
    async def clan_delete_prefix(
        self, ctx: commands.Context, clan_name: str, delete_discord_role: bool = False
    ):
        """Prefix fallback: !clan_delete <clan_name> [delete_discord_role]"""
        if not ctx.guild:
            await ctx.send("❌ Command must be used in a server.")
            return
        if not is_staff_user(ctx.author, ctx.guild):
            await ctx.send("❌ You must be an administrator or staff member.")
            return

        sub = self.service.search_submission(ctx.guild.id, clan_name)
        if not sub:
            await ctx.send(f"❌ No registered clan found matching `{clan_name}`.")
            return

        name = sub.clan_name
        role_msg = "Discord role kept intact."
        if delete_discord_role and sub.role_id:
            role = ctx.guild.get_role(sub.role_id)
            if role:
                try:
                    if role < ctx.guild.me.top_role:
                        await role.delete(reason=f"Clan {name} deleted by {ctx.author}")
                        role_msg = f"Role @{role.name} deleted."
                    else:
                        role_msg = "Could not delete role (hierarchy above bot)."
                except Exception as e:
                    role_msg = f"Could not delete role: {e}"

        self.service.delete_submission(sub.id)
        await self._refresh_clan_role_panel(ctx.guild)
        await ctx.send(f"✅ Deleted **{name}** from registry and updated Claim Role Panel. {role_msg}")

    # -------------------------------------------------------------------------
    # Command: /clan-sync-roles and !clan_sync_roles
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="clan-sync-roles",
        description="Admin: Scan server roles ending with '//', import all clans into the database, and link roles.",
    )
    @app_commands.describe(
        suffix="The role suffix to detect clans (default is '//')",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def clan_sync_roles_slash(
        self,
        interaction: discord.Interaction,
        suffix: str = "//",
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return
        if not is_staff_user(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ You must be an administrator or staff member.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        imported = []
        updated = []

        clean_suffix = suffix.strip()
        target_roles = [
            r for r in guild.roles
            if r.name.strip().endswith(clean_suffix) and not r.is_default() and not r.managed
        ]

        if not target_roles:
            await interaction.followup.send(
                f"⚠️ No server roles ending with `{clean_suffix}` were found in this server.",
                ephemeral=True,
            )
            return

        for role in target_roles:
            raw_name = role.name.strip()
            if raw_name.endswith(clean_suffix):
                clean_name = raw_name[:-len(clean_suffix)].strip()
            else:
                clean_name = raw_name

            if not clean_name:
                continue

            existing = next(
                (
                    s for s in self.service._submissions.values()
                    if s.guild_id == guild.id and (s.role_id == role.id or s.clan_name.lower() == clean_name.lower())
                ),
                None,
            )

            color_val = role.color.value if role.color.value != 0 else DEFAULT_CLAN_COLOR
            color_hex = f"#{color_val:06x}"

            if existing:
                existing.clan_name = clean_name
                existing.role_id = role.id
                existing.role_name = role.name
                existing.status = "approved"
                existing.color_int = color_val
                existing.color_hex = color_hex
                updated.append(clean_name)
            else:
                new_sub = ClanSubmission(
                    id=str(uuid.uuid4()),
                    guild_id=guild.id,
                    applicant_id=interaction.user.id,
                    applicant_name=str(interaction.user),
                    clan_name=clean_name,
                    color_hex=color_hex,
                    color_int=color_val,
                    metadata_text=f"Region: Global • Members: {len(role.members)}",
                    description_text=f"Official clan on {guild.name}.",
                    activities_motto="Ready for battle.",
                    logo_url="",
                    status="approved",
                    role_id=role.id,
                    role_name=role.name,
                )
                self.service._submissions[new_sub.id] = new_sub
                imported.append(clean_name)

        self.service._persist()
        await self._refresh_clan_role_panel(guild)

        all_clans = sorted(imported + updated, key=lambda c: c.lower())
        clans_display = "\n".join(f"• **{c}**" for c in all_clans)
        if len(clans_display) > 2000:
            clans_display = clans_display[:1990] + "..."

        embed = discord.Embed(
            title="🔄 Clan Roles Synchronized",
            color=DEFAULT_CLAN_COLOR,
            description=(
                f"Successfully scanned and synchronized **{len(target_roles)}** clan roles from the server!\n\n"
                f"• **New Clans Added:** `{len(imported)}`\n"
                f"• **Existing Clans Updated:** `{len(updated)}`\n\n"
                f"**Active Clans Synced ({len(all_clans)}):**\n"
                f"{clans_display}\n\n"
                "💡 *The Clan Role Assignment Panel in your channel has been updated live with all clans!*"
            ),
        )
        embed.set_footer(text=f"{config.organization_name} • Clan Alignment System")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.command(name="clan_sync_roles")
    async def clan_sync_roles_prefix(self, ctx: commands.Context, suffix: str = "//"):
        """Prefix fallback: !clan_sync_roles [suffix]"""
        if not ctx.guild:
            await ctx.send("❌ Command must be used in a server.")
            return
        if not is_staff_user(ctx.author, ctx.guild):
            await ctx.send("❌ You must be an administrator or staff member.")
            return

        guild = ctx.guild
        clean_suffix = suffix.strip()
        target_roles = [
            r for r in guild.roles
            if r.name.strip().endswith(clean_suffix) and not r.is_default() and not r.managed
        ]

        if not target_roles:
            await ctx.send(f"⚠️ No server roles ending with `{clean_suffix}` were found.")
            return

        imported = []
        updated = []
        for role in target_roles:
            raw_name = role.name.strip()
            if raw_name.endswith(clean_suffix):
                clean_name = raw_name[:-len(clean_suffix)].strip()
            else:
                clean_name = raw_name

            if not clean_name:
                continue

            existing = next(
                (
                    s for s in self.service._submissions.values()
                    if s.guild_id == guild.id and (s.role_id == role.id or s.clan_name.lower() == clean_name.lower())
                ),
                None,
            )

            color_val = role.color.value if role.color.value != 0 else DEFAULT_CLAN_COLOR
            color_hex = f"#{color_val:06x}"

            if existing:
                existing.clan_name = clean_name
                existing.role_id = role.id
                existing.role_name = role.name
                existing.status = "approved"
                existing.color_int = color_val
                existing.color_hex = color_hex
                updated.append(clean_name)
            else:
                new_sub = ClanSubmission(
                    id=str(uuid.uuid4()),
                    guild_id=guild.id,
                    applicant_id=ctx.author.id,
                    applicant_name=str(ctx.author),
                    clan_name=clean_name,
                    color_hex=color_hex,
                    color_int=color_val,
                    metadata_text=f"Region: Global • Members: {len(role.members)}",
                    description_text=f"Official clan on {guild.name}.",
                    activities_motto="Ready for battle.",
                    logo_url="",
                    status="approved",
                    role_id=role.id,
                    role_name=role.name,
                )
                self.service._submissions[new_sub.id] = new_sub
                imported.append(clean_name)

        self.service._persist()
        await self._refresh_clan_role_panel(guild)
        await ctx.send(
            f"✅ **Synced {len(target_roles)} clan roles!** ({len(imported)} added, {len(updated)} updated). "
            f"The Clan Role Assignment Panel is refreshed live."
        )

async def setup(bot: commands.Bot) -> None:
    service = getattr(bot, "clan_showcase_service", None)
    await bot.add_cog(ClanShowcaseCog(bot, service=service))

