import typing
import math
import discord
from redbot.core.utils.chat_formatting import box


# Get level from XP
def get_level(xp: int, base: int, exp: typing.Union[int, float]) -> int:
    return int((xp / base) ** (1 / exp))


# Get XP from level
def get_xp(level: int, base: int, exp: typing.Union[int, float]) -> int:
    return math.ceil(base * (level ** exp))


# Convert a hex color to an RGB tuple
def hex_to_rgb(color: str) -> tuple:
    color = color.strip("#")
    rgb = tuple(int(color[i: i + 2], 16) for i in (0, 2, 4))
    return rgb


# Format time from total seconds and format into readable string
def time_formatter(time_in_seconds) -> str:
    time_in_seconds = int(time_in_seconds)  # Some time differences get sent as a float so just handle it the dumb way
    minutes, seconds = divmod(time_in_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    years, days = divmod(days, 365)
    if not any([seconds, minutes, hours, days, years]):
        tstring = "None"
    elif not any([minutes, hours, days, years]):
        if seconds == 1:
            tstring = f"{seconds} second"
        else:
            tstring = f"{seconds} seconds"
    elif not any([hours, days, years]):
        if minutes == 1:
            tstring = f"{minutes} minute"
        else:
            tstring = f"{minutes} minutes"
    elif hours and not days and not years:
        tstring = f"{hours} hours, and {minutes} minutes"
    elif days and not years:
        tstring = f"{days} days {hours} hours {minutes} minutes"
    else:
        tstring = f"{years}y {days}d {hours}h {minutes}m"
    return tstring


async def get_user_position(conf: dict, user_id: str) -> dict:
    base = conf["base"]
    exp = conf["exp"]
    prestige_req = conf["prestige"]
    leaderboard = {}
    total_xp = 0
    user_xp = 0
    for user, data in conf["users"].items():
        xp = int(data["xp"])
        prestige = data["prestige"]
        if prestige:
            add_xp = get_xp(prestige_req, base, exp)
            xp = int(xp + (prestige * add_xp))
        leaderboard[user] = xp
        total_xp += xp
        if user == user_id:
            user_xp = xp
    sorted_users = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
    for i in sorted_users:
        if i[0] == user_id:
            percent = round((user_xp / total_xp) * 100, 2)
            pos = sorted_users.index(i) + 1
            pos_data = {"p": pos, "pr": percent}
            return pos_data


async def get_user_stats(conf: dict, user_id: str) -> dict:
    base = conf["base"]
    exp = conf["exp"]
    users = conf["users"]
    user = users[user_id]
    xp = int(user["xp"])
    messages = user["messages"]
    voice = user["voice"]
    voice = int(voice / 60)
    level = user["level"]
    prestige = user["prestige"]
    emoji = user["emoji"]
    if "stars" in user:
        stars = user["stars"]
    else:
        stars = 0
    next_level = level + 1
    xp_needed = get_xp(next_level, base, exp)
    ratio = xp / xp_needed
    lvlpercent = int(ratio * 100)
    blocks = int(30 * ratio)
    blanks = int(30 - blocks)
    lvlbar = "〘"
    for _ in range(blocks):
        lvlbar += "█"
    for _ in range(blanks):
        lvlbar += "-"
    lvlbar += "〙"
    stats = {
        "l": level,
        "m": messages,
        "v": voice,
        "xp": xp,
        "goal": xp_needed,
        "lb": lvlbar,
        "lp": lvlpercent,
        "e": emoji,
        "pr": prestige,
        "stars": stars
    }
    return stats


async def profile_embed(
        user,
        position,
        percentage,
        level,
        messages,
        voice,
        progress,
        lvlbar,
        lvlpercent,
        emoji,
        prestige,
        stars
) -> discord.Embed:
    msg = f"🎖｜Level {level}\n"
    if prestige:
        msg += f"🏆｜Prestige {prestige} {emoji}\n"
    msg += f"⭐｜{stars} rep\n" \
           f"💬｜{messages} messages sent\n" \
           f"🎙｜{voice} minutes in voice\n" \
           f"💡｜{progress} XP"
    embed = discord.Embed(
        title=f"{user.name}'s Profile",
        description=msg,
        color=user.colour
    )
    embed.add_field(name="Progress", value=box(f"{lvlbar} {lvlpercent} %", lang="python"))
    embed.set_thumbnail(url=user.avatar_url)
    if position:
        embed.set_footer(text=f"Rank: {position} with {percentage}% of global server XP")
    return embed

