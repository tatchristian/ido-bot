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

logger = logging.getLogger("uda_bot.clan_showcase_cog")


def is_staff_user(user: discord.User | discord.Member, guild: discord.Guild) -> bool:
    """Checks whether the user has administrator or staff privileges in the guild."""
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

    threshold_role = None
    if config.admin_role_id:
        threshold_role = guild.get_role(config.admin_role_id)
    if not threshold_role and config.admin_role_name:
        target_name = config.admin_role_name.strip().lower()
        threshold_role = discord.utils.find(
            lambda r: r.name.strip().lower() == target_name,
            guild.roles,
        )
    if threshold_role and member.top_role.position >= threshold_role.position:
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
        self.draft["is_auto"] = False
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
            placeholder="Enter your official Clan Name (e.g. Cerberus Elite)",
            default=self.initial_data.get("clan_name", self.initial_data.get("clan_name_color", "").split("|")[0].strip()),
            style=discord.TextStyle.short,
            max_length=100,
            required=True,
        )
        self.metadata = discord.ui.TextInput(
            label="Clan Metadata (Region, Leaders, Status)",
            placeholder=(
                "Region: [Region]\n"
                "Founded: [Date]\n"
                "Leader: [Leader IGN]\n"
                "Co-leaders: [Co-leaders]\n"
                "Status: Active"
            ),
            default=self.initial_data.get("metadata", ""),
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )
        self.description = discord.ui.TextInput(
            label="Clan Description & Backstory",
            placeholder="Describe your clan's backstory, vision, philosophy, and goals...",
            default=self.initial_data.get("description", ""),
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=True,
        )
        self.activities_motto = discord.ui.TextInput(
            label="Activities & Motto (Optional)",
            placeholder=(
                "• Main Activities (Tournaments, Scrims)\n"
                '• Motto: "Your clan motto here"'
            ),
            default=self.initial_data.get("activities_motto", ""),
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False,
        )
        self.logo_url = discord.ui.TextInput(
            label="Clan Logo / Emblem (Image Link)",
            placeholder="Paste image link (Pressing Submit opens a preview before full submission)",
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

        # 2. Determine initial color:
        # Default behavior: Always auto-detect from the logo image unless user explicitly picked a color
        color_override = self.selected_color
        is_auto = True if not color_override else False

        if not color_override and resolved_logo_url:
            raw_img_bytes = await fetch_image_bytes(resolved_logo_url)
            if raw_img_bytes:
                extracted = extract_dominant_color_from_bytes(raw_img_bytes)
                if extracted:
                    color_override = extracted[0]
                    is_auto = True
                    logger.info("Auto-detected color %s for clan '%s' from logo", color_override, self.clan_name.value)

        # Fallback to previously chosen manual color if auto-extract couldn't find a saturated shade
        if not color_override:
            prev_color = self.initial_data.get("clan_color")
            if prev_color and not self.initial_data.get("is_auto"):
                color_override = prev_color
                is_auto = False

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
            "is_auto": is_auto,
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
        ("auto", "🖼️ Auto-Detect from Clan Logo", "Extracts the dominant theme from your logo artwork"),
        ("#10b981", "🟢 Emerald Green (#10B981)", "Official UDA Emerald Green theme"),
        ("#d4af37", "🟡 Cerberus Gold (#D4AF37)", "Official Cerberus Gold theme"),
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
        is_auto = draft.get("is_auto", False)
        select_options = []
        for val, label, desc in self.COLOR_OPTIONS:
            if val == "auto":
                is_def = is_auto
                if is_auto and current_color:
                    label = f"🖼️ Auto-Detect ({current_color.upper()})"
            else:
                is_def = (not is_auto and val.lower() == current_color)
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
        selected = self.color_select.values[0]
        if selected == "auto":
            extracted_color = None
            logo_url = self.draft.get("logo_url", "")
            if logo_url:
                raw_bytes = await fetch_image_bytes(logo_url)
                if raw_bytes:
                    extracted = extract_dominant_color_from_bytes(raw_bytes)
                    if extracted:
                        extracted_color = extracted[0]
                        logger.info("Auto-detected color %s from logo %s via dropdown", extracted_color, logo_url)
                    else:
                        logger.warning("Could not extract vibrant color from %s bytes for logo %s", len(raw_bytes), logo_url)
                else:
                    logger.warning("Failed to fetch image bytes for logo %s", logo_url)
            new_hex = extracted_color or DEFAULT_CLAN_COLOR
            if isinstance(new_hex, int):
                new_hex = f"#{new_hex:06x}"
            self.draft["is_auto"] = True
        else:
            new_hex = selected
            self.draft["is_auto"] = False

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
            # Check if role with this name already exists
            existing_role = discord.utils.find(
                lambda r: r.name.strip().lower() == sub.clan_name.strip().lower(),
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
                        "name": sub.clan_name[:100],
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
                            name=sub.clan_name[:100],
                            colour=role_color,
                            mentionable=True,
                            reason=f"Automatic Clan Role created upon approval of {sub.clan_name} by {interaction.user}",
                        )
                        role_notice = f"Created new clan role **{created_role.name}**."
                    except Exception as fallback_exc:
                        logger.warning("Failed to automatically create clan role for %s: %s", sub.clan_name, fallback_exc)
                        role_notice = "*(Bot could not create clan role due to hierarchy or permissions)*"

            # Assign role to clan leader / applicant
            if created_role and applicant:
                try:
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
            else:
                prev = self.service.get_applicant_submission(interaction.guild.id, interaction.user.id)
                if prev:
                    initial_data = {
                        "clan_name": prev.clan_name,
                        "clan_color": prev.color_hex,
                        "metadata": prev.metadata_text,
                        "description": prev.description_text,
                        "activities_motto": prev.activities_motto,
                        "logo_url": prev.logo_url,
                    }
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
                # 1. Check if user has an unconfirmed draft to restore
                draft = self.service.get_draft(interaction.guild.id, interaction.user.id)
                if draft:
                    initial_data = draft
                else:
                    # 2. Check if user has an existing/pending submission to pre-fill
                    prev = self.service.get_applicant_submission(interaction.guild.id, interaction.user.id)
                    if prev:
                        initial_data = {
                            "clan_name": prev.clan_name,
                            "clan_color": prev.color_hex,
                            "metadata": prev.metadata_text,
                            "description": prev.description_text,
                            "activities_motto": prev.activities_motto,
                            "logo_url": prev.logo_url,
                        }

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
        self.bot.add_view(panel_view)
        self.bot.add_view(review_view)
        logger.info("Registered persistent clan showcase views (Submit Panel & Review Buttons).")

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
                "• **Interactive Color & Theme:** You will be able to preview and select your color theme (or auto-detect from your logo) directly on your live preview card before confirming!\n"
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
                "• **Interactive Color & Theme:** You will be able to preview and select your color theme (or auto-detect from your logo) directly on your live preview card before confirming!\n"
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

async def setup(bot: commands.Bot) -> None:
    service = getattr(bot, "clan_showcase_service", None)
    await bot.add_cog(ClanShowcaseCog(bot, service=service))

