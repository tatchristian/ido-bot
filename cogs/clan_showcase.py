"""
Clan Showcase Cog for IDO Tournament Bot (DUKE).
Provides interactive modal submission for clan profiles, persistent review panels,
and automated publishing matching the official Sapphire-style clan showcase embeds.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from services.clan_showcase_service import (
    DEFAULT_CLAN_COLOR,
    ClanShowcaseService,
    ClanSubmission,
    build_clan_showcase_embed,
    parse_name_and_color,
    validate_image_url,
)

logger = logging.getLogger("ido_bot.clan_showcase_cog")


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


class ClanSubmissionModal(discord.ui.Modal, title="Clan Showcase Submission"):
    """
    5-field modal form for clan leaders to submit or draft their clan profile.
    Pre-fills previous inputs or drafts so users never lose their work if they close out.
    """

    def __init__(
        self,
        service: ClanShowcaseService,
        initial_data: Optional[dict[str, str]] = None,
    ):
        super().__init__()
        self.service = service
        self.initial_data = initial_data or {}

        self.clan_name_color = discord.ui.TextInput(
            label="Clan Name (Color is Optional)",
            placeholder="Enter Clan Name (or Clan Name | #hex for custom color)",
            default=self.initial_data.get("clan_name_color", ""),
            style=discord.TextStyle.short,
            max_length=100,
            required=True,
        )
        self.metadata = discord.ui.TextInput(
            label="Clan Metadata (Region, Leaders, Status)",
            placeholder=(
                "Region: [Your Region, e.g. North America]\n"
                "Founded: [Month / Year, e.g. July 2026]\n"
                "Leader: [Leader Name / IGN]\n"
                "Co-leaders: [Co-leader Names / IGNs]\n"
                "Status: Active"
            ),
            default=self.initial_data.get("metadata", ""),
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )
        self.description = discord.ui.TextInput(
            label="Clan Description & Philosophy",
            placeholder="Describe your clan's backstory, vision, philosophy, and goals...",
            default=self.initial_data.get("description", ""),
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=True,
        )
        self.activities_motto = discord.ui.TextInput(
            label="Activities & Motto",
            placeholder=(
                "• Activity 1\n"
                "• Activity 2\n"
                "• Activity 3\n\n"
                'Motto: "Your clan motto here"'
            ),
            default=self.initial_data.get("activities_motto", ""),
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )
        self.logo_url = discord.ui.TextInput(
            label="Clan Logo / Emblem Direct Image URL",
            placeholder="https://... (Direct link to PNG, JPG, or Discord image)",
            default=self.initial_data.get("logo_url", ""),
            style=discord.TextStyle.short,
            max_length=500,
            required=True,
        )

        self.add_item(self.clan_name_color)
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

        # 1. Validate Image URL
        is_valid_url, url_error = validate_image_url(self.logo_url.value)
        if not is_valid_url:
            await interaction.response.send_message(
                f"❌ **Invalid Logo URL:** {url_error}\n"
                "Please make sure your link starts with `https://` or `http://` and points directly to an image (e.g. PNG, JPG, or Discord attachment).",
                ephemeral=True,
            )
            return

        # 2. Save draft so the user can re-open or edit anytime without losing text
        draft = {
            "clan_name_color": self.clan_name_color.value,
            "metadata": self.metadata.value,
            "description": self.description.value,
            "activities_motto": self.activities_motto.value,
            "logo_url": self.logo_url.value,
        }
        self.service.save_draft(guild.id, interaction.user.id, draft)

        # 3. Build Preview Embed
        clan_name, color_int, color_hex = parse_name_and_color(self.clan_name_color.value)
        preview_embed = build_clan_showcase_embed(
            clan_name=clan_name,
            color_int=color_int,
            metadata_text=self.metadata.value,
            description_text=self.description.value,
            activities_motto_text=self.activities_motto.value,
            logo_url=self.logo_url.value,
        )
        preview_embed.set_footer(
            text=f"{config.organization_name} • Clan Showcase Draft Preview"
        )

        # 4. Show ephemeral preview with Confirm, Edit, and Discard buttons
        confirm_view = ClanDraftConfirmationView(self.service, draft)
        await interaction.response.send_message(
            content=(
                "🔍 **Clan Profile Draft Preview**\n"
                "Review how your showcase looks below. **Your submission is NOT final until you click Confirm & Send to Staff.**\n"
                "If you need to make adjustments or fix a typo, click **Edit Draft** below:"
            ),
            embed=preview_embed,
            view=confirm_view,
            ephemeral=True,
        )


class ClanDraftConfirmationView(discord.ui.View):
    """
    Interactive ephemeral view allowing applicants to review their preview embed,
    edit their draft, or confirm official submission to staff.
    """

    def __init__(self, service: ClanShowcaseService, draft: dict[str, str]):
        super().__init__(timeout=600)
        self.service = service
        self.draft = draft

    @discord.ui.button(
        label="Confirm & Send to Staff",
        style=discord.ButtonStyle.success,
        emoji="🚀",
        custom_id="btn_confirm_clan_draft",
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
                activities_motto=self.draft["activities_motto"],
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
                activities_motto=self.draft["activities_motto"],
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
                f"• Staff will review your profile shortly. You will receive a direct message once approved!"
            ),
            embed=None,
            view=None,
        )

    @discord.ui.button(
        label="Edit Draft",
        style=discord.ButtonStyle.primary,
        emoji="✏️",
        custom_id="btn_edit_clan_draft",
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

        self.clan_name_color = discord.ui.TextInput(
            label="Clan Name & Color",
            default=f"{submission.clan_name} | {submission.color_hex}",
            placeholder="Clan Name (or Clan Name | #hex)",
            style=discord.TextStyle.short,
            max_length=100,
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
            label="Clan Description & Philosophy",
            default=submission.description_text,
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=True,
        )
        self.activities_motto = discord.ui.TextInput(
            label="Activities & Motto",
            default=submission.activities_motto,
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )
        self.logo_url = discord.ui.TextInput(
            label="Logo / Emblem Direct Image URL",
            default=submission.logo_url,
            style=discord.TextStyle.short,
            max_length=500,
            required=True,
        )

        self.add_item(self.clan_name_color)
        self.add_item(self.metadata)
        self.add_item(self.description)
        self.add_item(self.activities_motto)
        self.add_item(self.logo_url)

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Validate Image URL
        valid, err = validate_image_url(self.logo_url.value)
        if not valid:
            await interaction.response.send_message(
                f"❌ **Invalid Logo URL:** {err}", ephemeral=True
            )
            return

        # 2. Parse Name & Color
        new_name, new_color_int, new_color_hex = parse_name_and_color(
            self.clan_name_color.value
        )

        # 3. Update database record
        sub = self.service.update_submission(
            sub_id=self.submission.id,
            clan_name=new_name,
            color_hex=new_color_hex,
            color_int=new_color_int,
            metadata_text=self.metadata.value,
            description_text=self.description.value,
            activities_motto=self.activities_motto.value,
            logo_url=self.logo_url.value,
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

        # Update staff review message: disable buttons and display approver
        try:
            await interaction.message.edit(
                content=(
                    f"✅ **Approved by {interaction.user.mention}** on <t:{int(time.time())}:f>\n"
                    f"• **Clan:** **{sub.clan_name}**\n"
                    f"• **Applicant:** <@{sub.applicant_id}>\n"
                    f"• **Published in:** {showcase_channel.mention} ([Jump to Post]({showcase_msg.jump_url}))"
                ),
                view=None,
            )
        except Exception as exc:
            logger.warning("Could not edit staff review message: %s", exc)

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
                await applicant.send(
                    f"🎉 **Congratulations!** Your clan profile submission for **{sub.clan_name}** "
                    f"has been **approved** by staff in **{guild.name}**!\n\n"
                    f"It is now live in {showcase_channel.mention}!\n"
                    f"View your showcase here: {showcase_msg.jump_url}"
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


class ClanSubmissionPanelView(discord.ui.View):
    """
    Persistent view with the 'Submit Clan Profile' button.
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
                        "clan_name_color": f"{prev.clan_name} | {prev.color_hex}",
                        "metadata": prev.metadata_text,
                        "description": prev.description_text,
                        "activities_motto": prev.activities_motto,
                        "logo_url": prev.logo_url,
                    }

        modal = ClanSubmissionModal(self.service, initial_data=initial_data)
        await interaction.response.send_modal(modal)


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
    # Command: /post-clan-submission-panel and !post_clan_submission_panel
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="post-clan-submission-panel",
        description="Admin: Drop the interactive Clan Profile Submission panel with persistent button.",
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
                "Click the button below to submit your clan's profile for staff review.\n\n"
                "**Form Guidelines & Tips:**\n"
                "• **Clan Name:** Just enter your clan's name. *(Optional: if you have a custom team color, enter `Clan Name | #hex`, e.g. `Shadow | #ff0033`. Otherwise it automatically uses official IDO sky-blue!)*\n"
                "• **Metadata:** Enter region, founded date, and leaders. Plain names, IGNs, and @usernames are all accepted!\n"
                "• **Description & Motto:** Share your clan's philosophy, backstory, and activities.\n"
                "• **Logo URL:** Must be a direct image link (Discord upload, Imgur, PNG, or JPG).\n"
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
                "Click the button below to submit your clan's profile for staff review.\n\n"
                "**Form Guidelines & Tips:**\n"
                "• **Clan Name:** Just enter your clan's name. *(Optional: if you have a custom team color, enter `Clan Name | #hex`, e.g. `Shadow | #ff0033`. Otherwise it automatically uses official IDO sky-blue!)*\n"
                "• **Metadata:** Enter region, founded date, and leaders. Plain names, IGNs, and @usernames are all accepted!\n"
                "• **Description & Motto:** Share your clan's philosophy, backstory, and activities.\n"
                "• **Logo URL:** Must be a direct image link (Discord upload, Imgur, PNG, or JPG).\n"
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
    await bot.add_cog(ClanShowcaseCog(bot))

