"""
Automated Server Builder Service for IDO Tournament Community.
Replicates the official category and channel architecture with rate-limit throttling
and automated safeguards against 3v3 references.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable, Dict, List, Optional

import discord

logger = logging.getLogger("ido_bot.server_builder")

RATE_LIMIT_DELAY: float = 1.2

# Explicit layout specification directly conforming to the IDO template
LAYOUT_SPEC: List[Dict[str, Any]] = [
    {
        "category": None,
        "channels": [
            {"name": "🏆 ✾┊registration 📝", "type": "voice"},
            {"name": "✾┊💻-staff", "type": "text", "private": True},
            {"name": "👋｜welcome", "type": "text"},
            {"name": "📜┊official-clan_x_alliances-list", "type": "text"},
        ],
    },
    {
        "category": "🏛 ⭒-(I.D.O) ORGANIZATION HUB-⭒",
        "channels": [
            {"name": "📜❖┊rules", "type": "text"},
            {"name": "📣❖┊announcements", "type": "news"},
            {"name": "📢❖┊sub-announcements", "type": "news"},
            {"name": "⚖️✾┊ido-supreme-court 🏛", "type": "voice"},
            {"name": "📑-✾┊recruit-reports", "type": "text"},
            {"name": "🤖❖┊bot-guide ℹ️", "type": "text"},
        ],
    },
    {
        "category": "⭒-COMMUNITY HUB-⭒",
        "channels": [
            {"name": "🍵🌸┊general-chat", "type": "text"},
            {"name": "💬-🌸┊discussions-and-debates", "type": "voice"},
            {"name": "📷-🌸┊general-media", "type": "text"},
            {"name": "🎨📸🌸┊general-art", "type": "text"},
            {"name": "💸💖✾┊donations✾", "type": "text"},
            {"name": "🤖🌸┊bot-lounge- 🍸", "type": "text", "private": True},
        ],
    },
    {
        "category": "🏛 HALL--OF--CHAMPIONS 🏆",
        "channels": [
            {"name": "🌐✾┊ido-leaderboard", "type": "text"},
        ],
    },
    {
        "category": "🏰⭒hall-of-fame⭒",
        "channels": [
            {"name": "🤝 alliance-news", "type": "news"},
            {"name": "🌐🌸┊socials-and-promo🌸", "type": "text"},
            {"name": "💰✾┊trade-hub 💸", "type": "text"},
            {"name": "⚔️🌸┊solo-leveling", "type": "text"},
        ],
    },
    {
        "category": "✾voice-channel✾ 🔊",
        "channels": [
            {"name": "💪-✾┊Everyone✾", "type": "voice"},
            {"name": "🎶-✾┊VIBIN’✾", "type": "voice"},
            {"name": "🛋️-✾┊chillin’✾", "type": "voice"},
            {"name": "🔊・trio-lounge", "type": "voice", "user_limit": 3},
        ],
    },
    {
        "category": "Admin/Mod",
        "channels": [
            {"name": "✾┊tournament-committee", "type": "text", "private": True},
        ],
    },
]


def is_3v3_reference(text: str) -> bool:
    """
    Returns True if the text contains any 3v3 / 3ჸ3 / 3&3 variants
    which must be excluded according to organizational filter rules.
    """
    normalized = text.lower()
    patterns = [
        r"3[ჸ&xvX]3",
        r"3\s*[ჸ&xvX]\s*3",
        r"3\u1ce83",
    ]
    for pat in patterns:
        if re.search(pat, text, flags=re.IGNORECASE):
            return True
    return False


async def build_server_layout(
    guild: discord.Guild,
    log_callback: Optional[Callable[[str], None]] = None,
    delay: float = RATE_LIMIT_DELAY,
) -> Dict[str, Any]:
    """
    Builds the complete IDO server structure on the target guild.
    Ensures safe execution with rate limiting, idempotent skipping of existing channels,
    and fallback for announcement channels if the server is not a Community server.
    """
    def log(msg: str):
        logger.info(msg)
        if log_callback:
            try:
                log_callback(msg)
            except Exception as e:
                logger.debug("Error in log callback: %s", e)

    results = {
        "categories_created": 0,
        "categories_existing": 0,
        "channels_created": 0,
        "channels_existing": 0,
        "channels_skipped_filter": 0,
        "errors": [],
        "details": [],
    }

    bot_member = guild.me
    if not bot_member or not bot_member.guild_permissions.manage_channels:
        err = "Bot is missing 'Manage Channels' permission in target guild."
        log(f"❌ {err}")
        results["errors"].append(err)
        return results

    is_community = "COMMUNITY" in guild.features

    for group in LAYOUT_SPEC:
        cat_name = group.get("category")
        target_category: Optional[discord.CategoryChannel] = None

        if cat_name:
            if is_3v3_reference(cat_name):
                log(f"⏭️ Skipping category matching 3v3 filter: '{cat_name}'")
                results["channels_skipped_filter"] += 1
                continue

            # Check if category already exists (case-insensitive strip match)
            existing_cat = discord.utils.find(
                lambda c: c.name.strip().lower() == cat_name.strip().lower(),
                guild.categories,
            )

            if existing_cat:
                target_category = existing_cat
                results["categories_existing"] += 1
                log(f"📁 Category exists: '{cat_name}'")
            else:
                try:
                    target_category = await guild.create_category(name=cat_name)
                    results["categories_created"] += 1
                    log(f"✨ Created Category: '{cat_name}'")
                    await asyncio.sleep(delay)
                except Exception as e:
                    err = f"Failed to create category '{cat_name}': {e}"
                    log(f"❌ {err}")
                    results["errors"].append(err)
                    continue

        # Channels inside this group
        for ch_info in group.get("channels", []):
            ch_name = ch_info["name"]
            ch_type = ch_info.get("type", "text")
            user_limit = ch_info.get("user_limit", 0)
            is_private = ch_info.get("private", False)

            if is_3v3_reference(ch_name):
                log(f"⏭️ Skipping channel matching 3v3 filter: '{ch_name}'")
                results["channels_skipped_filter"] += 1
                continue

            # Check if channel already exists under this category or root
            existing_ch = None
            if target_category:
                existing_ch = discord.utils.find(
                    lambda c: c.name.strip().lower() == ch_name.strip().lower(),
                    target_category.channels,
                )
            else:
                existing_ch = discord.utils.find(
                    lambda c: c.name.strip().lower() == ch_name.strip().lower() and c.category is None,
                    guild.channels,
                )

            if existing_ch:
                results["channels_existing"] += 1
                log(f"  📌 Channel exists: '{ch_name}'")
                continue

            # Setup optional private overwrites (Staff / Admin channels)
            extra_kwargs: Dict[str, Any] = {}
            if is_private and guild.default_role:
                extra_kwargs["overwrites"] = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True),
                }

            try:
                if ch_type == "voice":
                    await guild.create_voice_channel(
                        name=ch_name,
                        category=target_category,
                        user_limit=user_limit,
                        **extra_kwargs,
                    )
                    log(f"  🔊 Created Voice Channel: '{ch_name}' (limit: {user_limit or 'unlimited'})")
                elif ch_type == "news":
                    # Attempt news channel if Community is active, fallback to standard text channel
                    if is_community:
                        try:
                            await guild.create_text_channel(
                                name=ch_name,
                                category=target_category,
                                news=True,
                                **extra_kwargs,
                            )
                            log(f"  📣 Created Announcement Channel: '{ch_name}'")
                        except Exception as ne:
                            logger.debug("News channel creation failed (%s), falling back to text: %s", ne, ch_name)
                            await guild.create_text_channel(
                                name=ch_name,
                                category=target_category,
                                **extra_kwargs,
                            )
                            log(f"  💬 Created Text Channel (news fallback): '{ch_name}'")
                    else:
                        await guild.create_text_channel(
                            name=ch_name,
                            category=target_category,
                            **extra_kwargs,
                        )
                        log(f"  💬 Created Text Channel: '{ch_name}'")
                else:
                    await guild.create_text_channel(
                        name=ch_name,
                        category=target_category,
                        **extra_kwargs,
                    )
                    log(f"  💬 Created Text Channel: '{ch_name}'")

                results["channels_created"] += 1
                await asyncio.sleep(delay)

            except Exception as e:
                err = f"Failed to create channel '{ch_name}': {e}"
                log(f"  ❌ {err}")
                results["errors"].append(err)

    log(
        f"🏁 Layout build complete! Created {results['categories_created']} categories, "
        f"{results['channels_created']} channels ({results['categories_existing']} categories and "
        f"{results['channels_existing']} channels already existed)."
    )
    return results
