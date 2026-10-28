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
    5-field modal form for clan leaders to submit their clan profile.
    Respects Discord's 5-component limit.
    """

    clan_name_color = discord.ui.TextInput(
        label="Clan Name & Hex Color",
        placeholder="Clan Name | Hex Color (e.g. Yume | #38bdf8)",
        style=discord.TextStyle.short,
        max_length=100,
        required=True,
    )
    metadata = discord.ui.TextInput(
        label="Clan Metadata (Region, Leaders, Status)",
        placeholder=(
            "Region: Mumbai, India\n"
            "Founded: 7 July\n"
            "Leader: Ragnarok\n"
            "Co-Leader: Aasri, Astral\n"
            "Status: Active"
        ),
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True,
    )
    description = discord.ui.TextInput(
        label="Clan Description & Philosophy",
        placeholder="Clan philosophy, backstory, and goals...",
        style=discord.TextStyle.paragraph,
        max_length=1500,
        required=True,
    )
    activities_motto = discord.ui.TextInput(
        label="Activities & Motto",
        placeholder=(
            "• Tournaments\n"
            "• Training Sessions\n"
            "• Scrims\n\n"
            'Motto: "Dream. Train. Dominate." 🌙'
        ),
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True,
    )
    logo_url = discord.ui.TextInput(
        label="Clan Logo / Emblem Direct Image URL",
        placeholder="Direct image URL (https://...)",
        style=discord.TextStyle.short,
        max_length=500,
        required=True,
    )

    def __init__(self, service: ClanShowcaseService):
        super().__init__()
        self.service = service

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

        # 2. Locate Staff Review Channel
        _, review_chan_id = self.service.get_guild_channels(guild.id)
        review_channel = None
        if review_chan_id:
            review_channel = guild.get_channel(review_chan_id)

        # Fallback search if channel id was not set
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

        # 3. Create Persistent Submission Record
        sub = self.service.create_submission(
            guild_id=guild.id,
            applicant_id=interaction.user.id,
            applicant_name=str(interaction.user),
            clan_name_color_raw=self.clan_name_color.value,
            metadata_text=self.metadata.value,
            description_text=self.description.value,
            activities_motto=self.activities_motto.value,
            logo_url=self.logo_url.value,
        )

        # 4. Immediate Ephemeral Confirmation
        await interaction.response.send_message(
            "✅ **Submission received! Sent to staff for review.**\n"
            f"Your submission ID is `{sub.id}`. You will receive a direct message once staff approves or reviews your clan showcase.",
            ephemeral=True,
        )

        # 5. Post Preview Embed & Action Buttons to Staff Review Channel
        preview_embed = sub.to_embed()
        # Add submission ID into the footer for staff reference & persistence fallback
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
            logger.info(
                "Posted clan submission %s by user %s to staff channel %s",
                sub.id,
                interaction.user.id,
                review_channel.id,
            )
        except Exception as exc:
            logger.error("Failed to post clan submission to staff review channel: %s", exc)


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
        modal = ClanSubmissionModal(self.service)
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
        description="Drop the interactive Clan Profile Submission panel with persistent button.",
    )
    @app_commands.describe(
        channel="Channel to post the submission panel in (defaults to current channel)"
    )
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
                "**Submission Guidelines:**\n"
                "• Must be an official Clan Leader or authorized representative.\n"
                "• Provide accurate metadata (Region, Founded Date, Leaders, Status).\n"
                "• Provide a valid direct image URL for your clan emblem / logo.\n"
                "• Submissions are reviewed by staff before being published to the showcase.\n\n"
                "Click **📋 Submit Clan Profile** below to open the submission form!"
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
                "**Submission Guidelines:**\n"
                "• Must be an official Clan Leader or authorized representative.\n"
                "• Provide accurate metadata (Region, Founded Date, Leaders, Status).\n"
                "• Provide a valid direct image URL for your clan emblem / logo.\n"
                "• Submissions are reviewed by staff before being published to the showcase.\n\n"
                "Click **📋 Submit Clan Profile** below to open the submission form!"
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
        description="Configure target showcase and staff review channels for this server.",
    )
    @app_commands.describe(
        showcase_channel="Public channel where approved clan embeds will be published",
        staff_review_channel="Private channel where staff review new clan submissions",
    )
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
        description="View current showcase and staff review channels for this server.",
    )
    async def view_clan_channels(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
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
    # Command: /clan-showcase-preview
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="clan-showcase-preview",
        description="Preview how a clan showcase embed will look before submitting.",
    )
    @app_commands.describe(
        clan_name="Clan Name (e.g. Yume)",
        hex_color="Hex color (e.g. #38bdf8)",
        logo_url="Direct image link for clan logo and emblem banner",
    )
    async def preview_showcase_embed(
        self,
        interaction: discord.Interaction,
        clan_name: str = "Yume",
        hex_color: str = "#38bdf8",
        logo_url: str = "https://i.imgur.com/8Q9Z5yZ.png",
    ):
        """Allows testing the Sapphire-identical embed format live."""
        _, color_int, _ = parse_name_and_color(f"{clan_name} | {hex_color}")
        demo_embed = build_clan_showcase_embed(
            clan_name=clan_name,
            color_int=color_int,
            metadata_text=(
                "Region: Mumbai, India\n"
                "Founded: 7 July\n"
                "Leader: Ragnarok\n"
                "Co-leader: Aasri, Astral, Nana, bread\n\n"
                "Status: Active"
            ),
            description_text=(
                f"{clan_name}, meaning \"Dream\" in Japanese, is a competitive clan built for players "
                "who strive to improve and reach the highest level. Home to some of the strongest players "
                "from the Mumbai server, we focus on discipline, teamwork, and constant growth. "
                "Through structured training, competitive events, and a merit-based grading system, "
                "every member has the opportunity to rise through the ranks and turn their dream into reality."
            ),
            activities_motto_text=(
                "• Competitive Clan Wars\n"
                "• Training Sessions\n"
                "• Player Development\n"
                "• Grade & Ranking System\n"
                "• Tournaments\n"
                "• Community Events\n\n"
                'Motto:\n"Dream. Train. Dominate." 🌙'
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
