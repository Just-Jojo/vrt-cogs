import asyncio
import contextlib
import json
import logging
import math
import os
import random
import shutil
import socket

import aiohttp
import discord
from rcon import Client
from dislash import (InteractionClient,
                     ActionRow,
                     Button,
                     ButtonStyle,
                     SelectMenu,
                     SelectOption)
from redbot.core import commands, Config, bank
from redbot.core.utils.chat_formatting import box, pagify

from .buttonmenus import (
    buttonmenu,
    bprev_page,
    bclose_menu,
    bnext_page,
    DEFAULT_BUTTON_CONTROLS
)
from .formatter import (
    shop_stats,
    dlist,
    rlist,
    TIPS,
    SHOP_ICON,
    SELECTORS,
    REACTIONS
)
from .menus import (
    menu,
    prev_page,
    close_menu,
    next_page,
    DEFAULT_CONTROLS
)

log = logging.getLogger("red.vrt.arkshop")

LOADING = "https://i.imgur.com/l3p6EMX.gif"


class ArkShop(commands.Cog):
    """
    Integrated Shop for Ark!
    """
    __author__ = "Vertyco"
    __version__ = "1.5.17"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        InteractionClient(bot)
        self.config = Config.get_conf(self, 117117, force_registration=True)
        default_global = {
            "main_server": None,
            "main_path": None,
            "clusters": {},
            "datashops": {},

        }
        default_guild = {
            "usebuttons": False,
            "shops": {},
            "logchannel": None,
            "users": {},
            "logs": {"items": {}, "users": {}}
        }
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        self.shop_controls = {
            "\N{LEFTWARDS ARROW WITH HOOK}\N{VARIATION SELECTOR-16}": self.go_back,
            "\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}": prev_page,
            "\N{CROSS MARK}": close_menu,
            "\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}": next_page,
            "\N{DIGIT ONE}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}": self.select_one,
            "\N{DIGIT TWO}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}": self.select_two,
            "\N{DIGIT THREE}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}": self.select_three,
            "\N{DIGIT FOUR}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}": self.select_four,
        }
        self.shop_button_controls = {
            "buttons": [
                ActionRow(
                    Button(
                        style=ButtonStyle.grey,
                        label="Back",
                        custom_id="back"
                    ),
                    Button(
                        style=ButtonStyle.gray,
                        label="◀",
                        custom_id="prev"
                    ),
                    Button(
                        style=ButtonStyle.grey,
                        label="❌",
                        custom_id="exit"
                    ),
                    Button(
                        style=ButtonStyle.grey,
                        label="▶",
                        custom_id="next"
                    )
                ),
                ActionRow(
                    Button(
                        style=ButtonStyle.green,
                        label="\N{DIGIT ONE}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}",
                        custom_id="one"
                    ),
                    Button(
                        style=ButtonStyle.green,
                        label="\N{DIGIT TWO}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}",
                        custom_id="two"
                    ),
                    Button(
                        style=ButtonStyle.green,
                        label="\N{DIGIT THREE}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}",
                        custom_id="three"
                    ),
                    Button(
                        style=ButtonStyle.green,
                        label="\N{DIGIT FOUR}\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}",
                        custom_id="four"
                    )
                )
            ],
            "actions": {
                "back": self.go_back,
                "prev": bprev_page,
                "exit": bclose_menu,
                "next": bnext_page,
                "one": self.select_one,
                "two": self.select_two,
                "three": self.select_three,
                "four": self.select_four
            }
        }

    @staticmethod
    async def clear(ctx: commands.Context, message: discord.Message, reaction: str, user: discord.Member):
        perms = message.channel.permissions_for(ctx.me)
        if perms.manage_messages:
            with contextlib.suppress(discord.NotFound):
                await message.remove_reaction(reaction, user)

    @staticmethod
    async def clearall(ctx, message: discord.Message):
        perms = message.channel.permissions_for(ctx.me)
        try:
            if perms.manage_messages:
                await message.clear_reactions()
            else:
                for r in REACTIONS:
                    await message.remove_reaction(r, ctx.me)
                    await asyncio.sleep(1)
        except discord.Forbidden:
            return
        except discord.NotFound:
            return
        except discord.HTTPException:
            pass
        return

    # Check if arktools is installed and loaded
    async def arktools(self, ctx: commands.Context = None):
        arktools = self.bot.get_cog("ArkTools")
        if arktools:
            return arktools
        else:
            embed = discord.Embed(
                title="ArkTools Not Loaded!",
                description="The `ArkTools` cog is required for this cog to function, "
                            "please install that first and load it.",
                color=discord.Color.red()
            )
            if ctx:
                await ctx.send(embed=embed)
            return None

    # Iterate through arktools config and find player XUID
    async def get_xuid_from_arktools(self, ctx):
        arktools = await self.arktools(ctx)
        if not arktools:
            return None
        playerdata = await arktools.config.guild(ctx.guild).players()
        for xuid, data in playerdata.items():
            if "discord" in data:
                if ctx.author.id == data["discord"]:
                    return xuid
        else:
            embed = discord.Embed(
                description=f"Your discord ID has not been found in the database.\n"
                            f"Please register with `{ctx.prefix}register`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return None

    # Returns a list of tuples containing a channel object and implant ID string
    async def get_implants_from_user(self, ctx, xuid: str) -> list:
        arktools = await self.arktools()
        if not arktools:
            return []
        stats = await arktools.config.guild(ctx.guild).players()
        user = stats[xuid]["ingame"]
        implants = []
        for channel_id, data in user.items():
            channel = ctx.guild.get_channel(int(channel_id))
            implant = data["implant"]
            if implant:
                implants.append((channel, implant))
        return implants

    async def get_types(self, ctx, shoptype):
        if shoptype == "rcon":
            title = "RCON Shop"
            tip = "Make sure you are ONLINE when purchasing from the RCON shop!"
            categories = await self.config.guild(ctx.guild).shops()
        else:
            title = "Data Shop"
            tip = "Remember to empty your Ark data before purchasing stuff!"
            categories = await self.config.datashops()
        return title, tip, categories

    @commands.command(name="dshoplist")
    @commands.guild_only()
    async def data_status(self, ctx):
        """List all items in the data shop"""
        if ctx.guild.id != await self.config.main_server():
            embed = discord.Embed(
                description="This is not the main server!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        shops = await self.config.datashops()
        if len(shops.keys()) == 0:
            embed = discord.Embed(
                description="There is no data for this server yet!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        pages = await dlist(shops)
        if await self.config.guild(ctx.guild).usebuttons():
            await buttonmenu(ctx, pages, DEFAULT_BUTTON_CONTROLS)
        else:
            await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="rshoplist")
    @commands.guild_only()
    async def rcon_status(self, ctx):
        """List all items in the rcon shop"""
        shops = await self.config.guild(ctx.guild).shops()
        if not shops:
            embed = discord.Embed(
                description="There is no data for this server yet!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        if len(shops.keys()) == 0:
            embed = discord.Embed(
                description="There are no items available yet!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        pages = await rlist(shops)
        if await self.config.guild(ctx.guild).usebuttons():
            await buttonmenu(ctx, pages, DEFAULT_BUTTON_CONTROLS)
        else:
            await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.group(name="shopset")
    @commands.admin()
    @commands.guild_only()
    async def _shopset(self, ctx):
        """Base Ark Shop Setup Command"""
        await self.arktools(ctx)
        pass

    @_shopset.command(name="view")
    @commands.admin()
    @commands.guild_only()
    async def view_settings(self, ctx: commands.Context):
        """View ArkShop settings"""
        guild = ctx.guild
        conf = await self.config.guild(guild).all()
        log_channel = conf["logchannel"]
        if log_channel:
            log_channel = guild.get_channel(log_channel)
            if log_channel:
                log_channel = log_channel.mention
            else:
                log_channel = "#deleted-channel"

        main_server = await self.config.main_server()
        main_guild = self.bot.get_guild(int(main_server))
        if main_guild:
            main = main_guild.name
        else:
            main = main_server
        embed = discord.Embed(
            title="ArkShop Settings",
            description=f"`Log Channel:      `{log_channel}\n"
                        f"`Users Registered: `{len(conf['users'].keys())}\n"
                        f"`Main Server:   `{main}",
            color=discord.Color.random()
        )
        if guild.id == main_server:
            main_path = await self.config.main_path()
            clusters = await self.config.clusters()
            clist = ""
            for c, p in clusters.items():
                clist += f"{c}: {p}\n"
            embed.add_field(
                name="Main Path",
                value=box(main_path, lang='python'),
                inline=False
            )
            embed.add_field(
                name="Cluster Paths",
                value=box(clist, lang='python'),
                inline=False
            )
        await ctx.send(embed=embed)

    @_shopset.command(name="usebuttons")
    @commands.admin()
    async def toggle_buttons(self, ctx: commands.Context):
        """
        (Toggle) use of buttons

        ArkTools will use buttons instead of reactions
        """
        buttons = await self.config.guild(ctx.guild).usebuttons()
        if buttons:
            await self.config.guild(ctx.guild).usebuttons.set(False)
            await ctx.send("ArkShop will no longer use buttons")
        else:
            await self.config.guild(ctx.guild).usebuttons.set(True)
            await ctx.send("ArkShop will now use buttons")

    @_shopset.command(name="fullbackup")
    @commands.is_owner()
    async def backup_all_settings(self, ctx: commands.Context):
        """
        Backup global cog data

        Sends a full backup of the config as a JSON file to Discord.
        """
        settings = await self.config.all_guilds()
        settings = json.dumps(settings)
        filename = f"{ctx.guild}_full_config.json"
        with open(filename, "w") as file:
            file.write(settings)
        with open(filename, "rb") as file:
            await ctx.send(file=discord.File(file, filename))
        try:
            os.remove(filename)
        except Exception as e:
            log.warning(f"Failed to delete txt file: {e}")

    @_shopset.command(name="fullrestore")
    @commands.is_owner()
    async def restore_all_settings(self, ctx: commands.Context):
        """
        Restore a global backup

        Upload a backup JSON file attached to this command to restore the full config.
        """
        if ctx.message.attachments:
            attachment_url = ctx.message.attachments[0].url
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    config = await resp.json()
            for guild_id, data in config.items():
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    continue
                await self.config.guild(guild).set(data)
            return await ctx.send("Config restored from backup file!")
        else:
            return await ctx.send("Attach your backup file to the message when using this command.")

    @_shopset.command(name="dbackup")
    @commands.is_owner()
    async def backup_data_settings(self, ctx: commands.Context):
        """
        Backup Data shop

        Sends a full backup of the DATA shop config as a JSON file to Discord.
        """
        settings = await self.config.all()
        settings = json.dumps(settings)
        filename = f"{ctx.guild}_datashop_config.json"
        with open(filename, "w") as file:
            file.write(settings)
        with open(filename, "rb") as file:
            await ctx.send(file=discord.File(file, filename))
        try:
            os.remove(filename)
        except Exception as e:
            log.warning(f"Failed to delete txt file: {e}")

    @_shopset.command(name="drestore")
    @commands.is_owner()
    async def restore_data_settings(self, ctx: commands.Context):
        """
        Restore the Data shop

        Upload a backup JSON file attached to this command to restore the data shop config.
        """
        if ctx.message.attachments:
            attachment_url = ctx.message.attachments[0].url
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    config = await resp.json()
            await self.config.set(config)
            return await ctx.send("Config restored from backup file!")
        else:
            return await ctx.send("Attach your backup file to the message when using this command.")

    @_shopset.command(name="rbackup")
    @commands.guildowner()
    async def backup_settings(self, ctx: commands.Context):
        """
        Backup RCON shop guild cog data

        Sends a backup of the config as a JSON file to Discord.
        """
        settings = await self.config.guild(ctx.guild).all()
        settings = json.dumps(settings)
        filename = f"{ctx.guild}_RCON_config.json"
        with open(filename, "w") as file:
            file.write(settings)
        with open(filename, "rb") as file:
            await ctx.send(file=discord.File(file, filename))
        try:
            os.remove(filename)
        except Exception as e:
            log.warning(f"Failed to delete txt file: {e}")

    @_shopset.command(name="rrestore")
    @commands.guildowner()
    async def restore_settings(self, ctx: commands.Context):
        """
        Restore the RCON shop

        Upload an RCON shop backup JSON file attached to this command to restore the config.
        """
        if ctx.message.attachments:
            attachment_url = ctx.message.attachments[0].url
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    config = await resp.json()
            await self.config.guild(ctx.guild).set(config)
            return await ctx.send("Config restored from backup file!")
        else:
            return await ctx.send("Attach your backup file to the message when using this command.")

    @_shopset.command(name="mainserver")
    @commands.is_owner()
    async def set_main_server(self, ctx):
        """Set the Main Server for the data shop"""
        await self.config.main_server.set(ctx.guild.id)
        return await ctx.send(f"**{ctx.guild}** is now set as the main server!")

    @_shopset.group(name="data")
    @commands.is_owner()
    async def _datashopset(self, ctx):
        """Base Data Shop Setup Command"""
        check = await self.config.main_server()
        # check if main server has been set
        if check is None:
            embed = discord.Embed(
                title="Main Server Not Set",
                description="The Data Shop portion of this cog needs a main server set by the bot owner.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        # check if command was used in main server
        elif check != ctx.guild.id:
            embed = discord.Embed(
                title="Not Main Server",
                description="This feature can only be used on the main bot owner server!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        else:
            pass

    @_shopset.group(name="file")
    @commands.admin()
    async def _file(self, ctx):
        """
        Manage and create data packs for use in the data shop

        To create a pack follow these steps:
        1. Make the pack in-game manually, put what you want in the pack in your ark data.
        2. Upload the pack with the `upload` subcommand. (pack name will be the actual file and shop name). This will
        move the file from the cluster folder into the "MainPath" folder you set the cog to.
        3. Add the item to the data shop, make sure the item(or option name if item has options) is the exact same name
        as the file name.
        3. For other management tools, see the commands below.
        """
        check = await self.config.main_server()
        # check if main server has been set
        if check is None:
            embed = discord.Embed(
                title="Main Server Not Set",
                description="The Data Shop portion of this cog needs a main server set by the bot owner.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        # check if command was used in main server
        elif check != ctx.guild.id:
            embed = discord.Embed(
                title="Not Main Server",
                description="This feature can only be used on the main bot owner server!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        else:
            pass

    @_shopset.group(name="rcon")
    @commands.admin()
    async def _rconshopset(self, ctx):
        """Base RCON Shop Setup Command"""
        pass

    @_shopset.command(name="logchannel")
    @commands.guildowner()
    async def set_log_channel(self, ctx, channel: discord.TextChannel):
        """Set a log channel for all purchases to be logged to"""
        await self.config.guild(ctx.guild).logchannel.set(channel.id)
        await ctx.send(f"Log channle set to {channel.mention}")

    @_shopset.command(name="wipelogs")
    @commands.guildowner()
    async def wipe_logs(self, ctx):
        """Wipe shop logs/user logs"""
        async with self.config.guild(ctx.guild).logs() as logs:
            # wipe item logs
            logs["items"].clear()

            # wipe user logs
            logs["users"].clear()

            return await ctx.send("All logs wiped!")

    @_datashopset.command(name="mainpath")
    async def set_main_path(self, ctx, *, path):
        """Set main path for Data Pack folder"""
        await self.config.main_path.set(path)
        return await ctx.send(f"DataPack path has been set as:\n`{path}`")

    @_datashopset.command(name="addcluster")
    async def add_cluster(self, ctx, cluster_name, *, path):
        """Add a cluster path to the Data Shop"""
        arktools = await self.arktools(ctx)
        if not arktools:
            return
        clusters = await arktools.config.guild(ctx.guild).clusters()
        for cluster in clusters:
            # check if cluster exists in arktools config
            if cluster == cluster_name:
                break
        else:
            return await ctx.send(f"{cluster_name} Cluster does not exist, check your ArkTools settings.")

        # set path for cluster
        async with self.config.clusters() as clusters:
            clusters[cluster_name] = path
            return await ctx.send(f"{cluster} cluster path set as:\n`{path}`")

    @_datashopset.command(name="delcluster")
    async def delete_cluster(self, ctx, cluster_name):
        """Delete a cluster path from the Data Shop"""
        async with self.config.clusters() as clusters:
            for cluster in clusters:

                # check if cluster exists
                if cluster_name == cluster:
                    del clusters[cluster]
                    return await ctx.send(f"{cluster_name} cluster deleted!")
            else:
                return await ctx.send(f"Cluster name `{cluster_name}` not found!")

    @_file.command(name="upload")
    async def upload_pack(self, ctx, clustername, packname, xuid):
        """
        Upload/Create a pre-made pack from your ark data.

        Pack name will be the actual file name and xuid is your xuid
        If the pack name already exists, it will be overwritten by the new pack
        """
        destination_dir = await self.config.main_path()
        item_destination = os.path.join(destination_dir, packname)
        clusters = await self.config.clusters()
        # check if clustername exists
        if clustername not in clusters:
            clist = ""
            for clustername in clusters:
                clist += f"`{clustername}`\n"
            return await ctx.send(f"Invalid clustername, try one of these instead:\n"
                                  f"{clist}")
        source_dir = clusters[clustername]
        item_source_file = os.path.join(source_dir, xuid)
        # check source dir
        if not os.path.exists(source_dir):
            return await ctx.send("Source path does not exist!")
        # check destination dir
        if not os.path.exists(destination_dir):
            return await ctx.send("Destination path does not exist!")
        # move/replace pack
        if os.path.exists(item_destination):
            try:
                os.remove(item_destination)
                shutil.move(item_source_file, item_destination)
                return await ctx.send(f"Pack uploaded and overwritten as `{packname}`")
            except Exception as e:
                return await ctx.send(f"Data upload failed!\nError: {e}")
        else:
            shutil.move(item_source_file, item_destination)
            return await ctx.send(f"Pack uploaded and saved as `{packname}`")

    @_file.command(name="check")
    async def check_player_data(self, ctx, clustername, xuid):
        """
        Check a player's in-game data to see if there is anything in it

        If file size is anything other than 0, then there is something in their data.
        """
        clusters = await self.config.clusters()
        # check if clustername exists
        if clustername not in clusters:
            clist = ""
            for clustername in clusters:
                clist += f"`{clustername}`\n"
            return await ctx.send(f"Invalid clustername, try one of these instead:\n"
                                  f"{clist}")
        source_dir = clusters[clustername]
        if not os.path.exists(source_dir):
            embed = discord.Embed(
                description=f"Cluster path does not exist!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        player_data_file = os.path.join(source_dir, xuid)
        if not os.path.exists(player_data_file):
            embed = discord.Embed(
                description=f"Player has no data saved.",
                color=discord.Color.blue()
            )
            return await ctx.send(embed=embed)
        size = os.path.getsize(player_data_file)
        size = "{:,}".format(int(size))
        embed = discord.Embed(
            description=f"Player data size: `{size} bytes`",
            color=discord.Color.blue()
        )
        return await ctx.send(embed=embed)

    @_file.command(name="send")
    async def send_pack(self, ctx, clustername, packname, xuid):
        """Send a data pack to a player manually"""
        source_dir = await self.config.main_path()
        item_source_file = os.path.join(source_dir, packname)
        clusters = await self.config.clusters()
        # check if clustername exists
        if clustername not in clusters:
            clist = ""
            for clustername in clusters:
                clist += f"`{clustername}`\n"
            embed = discord.Embed(
                description=f"Invalid clustername, try one of these instead:\n"
                            f"{clist}",
                color=discord.Color.orange()
            )
            return await ctx.send(embed=embed)
        destination_dir = clusters[clustername]
        item_destination = os.path.join(destination_dir, xuid)
        # check source dir
        if not os.path.exists(source_dir):
            return await ctx.send("Source path does not exist!")
        # check destination dir
        if not os.path.exists(destination_dir):
            return await ctx.send("Destination path does not exist!")
        # check source file
        if not os.path.exists(item_source_file):
            embed = discord.Embed(
                description=f"Data file does not exist!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        # remove any existing data from destination
        if os.path.exists(item_destination):
            try:
                os.remove(item_destination)
                shutil.copyfile(item_source_file, item_destination)
                embed = discord.Embed(
                    description=f"Pack sent to XUID: `{xuid}`",
                    color=discord.Color.blue()
                )
                return await ctx.send(embed=embed)
            except Exception as e:
                return await ctx.send(f"Data send failed!\nError: {e}")
        else:
            shutil.copyfile(item_source_file, item_destination)
            embed = discord.Embed(
                description=f"Pack sent to XUID: `{xuid}`",
                color=discord.Color.blue()
            )
            return await ctx.send(embed=embed)

    @_file.command(name="listpacks")
    async def list_packs(self, ctx, packname=None):
        """List data packs in the main path as well as their file size"""
        path = await self.config.main_path()
        packs = os.listdir(path)
        if not packname:
            packlist = ""
            for pack in packs:
                fullpath = os.path.join(path, pack)
                size = os.path.getsize(fullpath)
                packlist += f"{pack} - {size}\n"
            if packlist:
                packlist = f"NAME - SIZE IN BYTES\n{packlist}"
                for p in pagify(packlist):
                    embed = discord.Embed(
                        title="NAME - SIZE IN BYTES",
                        description=box(p, lang="python")
                    )
                    await ctx.send(embed=embed)
        else:
            packlist = ""
            for pack in packs:
                if pack.lower() == packname.lower():
                    fullpath = os.path.join(path, packname)
                    size = os.path.getsize(fullpath)
                    packlist += f"**{pack}:** `{size}` Bytes"
            if packlist:
                await ctx.send(f"NAME - SIZE IN BYTES\n{packlist}")
            else:
                await ctx.send("No packs found!")

    @_file.command(name="rename")
    async def rename_pack(self, ctx, current_name, new_name):
        """Rename a data pack"""
        directory = await self.config.main_path()
        oldfile = os.path.join(directory, current_name)
        newfile = os.path.join(directory, new_name)
        if os.path.exists(oldfile):
            try:
                os.rename(oldfile, newfile)
                return await ctx.send(f"`{current_name}` pack renamed to `{new_name}`")
            except Exception as e:
                return await ctx.send(f"Failed to rename file!\nError: {e}")
        else:
            return await ctx.send("File not found!")

    @_file.command(name="copyplayerdata")
    async def copy_player_data(self, ctx, clustername, source_xuid, destination_xuid):
        """
        Copy a players ark data to your own.

        useful for checking other players data for various reasons
        """
        clusters = await self.config.clusters()
        # check if clustername exists
        if clustername not in clusters:
            clist = ""
            for clustername in clusters:
                clist += f"`{clustername}`\n"
            embed = discord.Embed(
                description=f"Invalid clustername, try one of these instead:\n"
                            f"{clist}",
                color=discord.Color.orange()
            )
            return await ctx.send(embed=embed)
        directory = clusters[clustername]
        source = os.path.join(directory, source_xuid)
        target = os.path.join(directory, destination_xuid)
        # check source file
        if not os.path.exists(source):
            embed = discord.Embed(
                description="Source file does not exist!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        # check if target already exists
        if os.path.exists(target):
            os.remove(target)
        shutil.copyfile(source, target)
        embed = discord.Embed(
            description=f"Player data from `{source_xuid}` copied to `{destination_xuid}`",
            color=discord.Color.blue()
        )
        return await ctx.send(embed=embed)

    @_file.command(name="delete")
    async def delete_pack(self, ctx, packname):
        """Delete a data pack"""
        directory = await self.config.main_path()
        file = os.path.join(directory, packname)
        if os.path.exists(file):
            try:
                os.remove(file)
                return await ctx.send(f"`{packname}` removed.")
            except Exception as e:
                return await ctx.send(f"Failed to delete datapack!\nError: {e}")
        else:
            return await ctx.send("File not found!")

    @_file.command(name="wipeplayerdata")
    async def wipe_player_data(self, ctx, clustername, player_xuid):
        """Wipe a players Ark data"""
        clusters = await self.config.clusters()
        # check if clustername exists
        if clustername not in clusters:
            clist = ""
            for clustername in clusters:
                clist += f"`{clustername}`\n"
            embed = discord.Embed(
                description=f"Invalid clustername, try one of these instead:\n"
                            f"{clist}",
                color=discord.Color.orange()
            )
            return await ctx.send(embed=embed)
        directory = clusters[clustername]
        file = os.path.join(directory, player_xuid)
        if os.path.exists(file):
            try:
                os.remove(file)
                return await ctx.send(f"Player data matching XUID `{player_xuid}` has been wiped.")
            except Exception as e:
                return await ctx.send(f"Failed to delete player data!\nError: {e}")
        else:
            return await ctx.send("File not found!")

    @_datashopset.command(name="addcategory")
    async def add_category(self, ctx, shop_name):
        """Add a data shop category"""
        async with self.config.datashops() as shops:
            if shop_name in shops:
                return await ctx.send(f"{shop_name} shop already exists!")
            else:
                shops[shop_name] = {}
                return await ctx.send(f"{shop_name} shop created!")

    @_datashopset.command(name="delcategory")
    async def delete_category(self, ctx, shop_name):
        """Delete a data shop category"""
        async with self.config.datashops() as shops:
            if shop_name in shops:
                del shops[shop_name]
                return await ctx.send(f"{shop_name} shop removed!")
            else:
                return await ctx.send(f"{shop_name} shop doesn't exist!")

    @_datashopset.command(name="renamecategory")
    async def rename_category(self, ctx, current_name, new_name):
        """Rename a data shop category"""
        async with self.config.datashops() as shops:
            if current_name in shops:
                shops[new_name] = shops.pop(current_name)
                return await ctx.send(f"{current_name} shop has been renamed to {new_name}!")
            else:
                return await ctx.send(f"{current_name} shop doesn't exist!")

    @_datashopset.command(name="additem")
    async def add_data_item(self, ctx, category, item_name, price=None):
        """
        Add an item to the data shop

        Use quotes if item name has spaces

        If item has options, the item name doesn't have to match the file name and you can leave out the price
        """
        async with self.config.datashops() as shops:
            # check if shop exists
            if category not in shops:
                return await ctx.send(f"{category} category not found!")
            # check if item exists
            if item_name in shops[category]:
                return await ctx.send(f"{item_name} item already exists!")
            if price:
                shops[category][item_name] = {"price": price, "options": {}}
                currency_name = await bank.get_currency_name(ctx.guild)
                return await ctx.send(
                    f"{item_name} has been added to the {category} shop for {price} {currency_name}"
                )
            else:
                shops[category][item_name] = {"price": False, "options": {}}
                return await ctx.send(
                    f"{item_name} has been added to the {category} shop with options.\n"
                    f"You will need to add options to it with `{ctx.prefix}shopset data addoption`"
                )

    @_datashopset.command(name="description")
    async def add_data_description(self, ctx, category, item_name, *, description: str):
        """Add a descriptin to a data shop item"""
        async with self.config.datashops() as shops:
            # check if shop exists
            if category not in shops:
                return await ctx.send(f"{category} category not found!")
                # check if item exists
            if item_name not in shops[category]:
                return await ctx.send(f"{item_name} item not found!")
            if "desc" in shops[category][item_name]:
                overwrite = "overwritten"
            else:
                overwrite = "set"
            shops[category][item_name]["desc"] = description
            await ctx.send(f"Description has been {overwrite} for {item_name} in the {category} category")

    @_datashopset.command(name="delitem")
    async def delete_data_item(self, ctx, shop_name, item_name):
        """Delete an item from a shop, whether it has options or not"""
        async with self.config.datashops() as shops:
            # check if shop exists
            if shop_name not in shops:
                return await ctx.send(f"{shop_name} shop not found!")
            # check if item exists
            elif item_name not in shops[shop_name]:
                return await ctx.send(f"{item_name} item not found!")
            else:
                del shops[shop_name][item_name]
                return await ctx.tick()

    @_datashopset.command(name="addoption")
    async def add_data_item_option(self, ctx, shop_name, item_name, option, price):
        """Add an option to an existing item in the data shop"""
        async with self.config.datashops() as shops:
            # check if shop exists
            if shop_name not in shops:
                return await ctx.send(f"{shop_name} shop not found!")
            # check if item exists
            elif item_name not in shops[shop_name]:
                return await ctx.send(f"{item_name} item not found!")
            # check if option exists
            elif option in shops[shop_name][item_name]["options"]:
                return await ctx.send(f"{option} option already exists!")
            else:
                shops[shop_name][item_name]["options"][option] = price
                return await ctx.tick()

    @_datashopset.command(name="deloption")
    async def del_data_item_option(self, ctx, shop_name, item_name, option):
        """Delete an option from an existing item in the data shop"""
        async with self.config.datashops() as shops:
            # check if shop exists
            if shop_name not in shops:
                return await ctx.send(f"{shop_name} shop not found!")
            # check if item exists
            elif item_name not in shops[shop_name]:
                return await ctx.send(f"{item_name} item not found!")
            # check if option exists
            elif option not in shops[shop_name][item_name]["options"]:
                return await ctx.send(f"{option} option not found!")
            else:
                del shops[shop_name][item_name]["options"][option]
                return await ctx.tick()

    @commands.command(name="setcluster")
    @commands.guild_only()
    async def set_cluster(self, ctx):
        """
        Set the cluster you play on

        This is so the cog knows where to send your data
        """
        arktools = await self.arktools(ctx)
        if not arktools:
            return
        clusters = await arktools.config.guild(ctx.guild).clusters()
        clist = ""
        for clustername in clusters:
            clist += f"`{clustername}`\n"
        if clist == "":
            return await ctx.send("No clusters have been created!")

        embed = discord.Embed(
            description=f"**Type one of the cluster names below.**\n"
                        f"{clist}",
            color=discord.Color.gold()
        )
        msg = await ctx.send(embed=embed)

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            reply = await self.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            ttl = "You took too long :yawning_face:"
            return await msg.edit(embed=discord.Embed(description=ttl))
        if reply.content.lower() not in clusters:
            noexist = "Cluster doesn't exist! Make sure you spelled it correctly."
            return await msg.edit(embed=discord.Embed(description=noexist))
        else:
            async with self.config.guild(ctx.guild).users() as users:
                users[ctx.author.id] = reply.content.lower()
                embed = discord.Embed(
                    description=f"**{reply.content}** cluster has been set for **{ctx.author.name}**!",
                    color=discord.Color.green()
                )
                return await msg.edit(embed=embed)

    @_rconshopset.command(name="addcategory")
    async def add_rcon_category(self, ctx, shop_name):
        """Add an rcon shop category"""
        async with self.config.guild(ctx.guild).shops() as shops:
            if shop_name in shops:
                return await ctx.send(f"{shop_name} shop already exists!")
            else:
                shops[shop_name] = {}
                return await ctx.send(f"{shop_name} shop created!")

    @_rconshopset.command(name="delcategory")
    async def delete_rcon_category(self, ctx, shop_name):
        """Delete an rcon shop category"""
        async with self.config.guild(ctx.guild).shops() as shops:
            if shop_name in shops:
                del shops[shop_name]
                return await ctx.send(f"{shop_name} shop removed!")
            else:
                return await ctx.send(f"{shop_name} shop doesn't exist!")

    @_rconshopset.command(name="renamecategory")
    async def rename_rcon_category(self, ctx, current_name, new_name):
        """Rename an rcon shop category"""
        async with self.config.guild(ctx.guild).shops() as shops:
            if current_name in shops:
                shops[new_name] = shops.pop(current_name)
                return await ctx.send(f"{current_name} shop has been renamed to {new_name}!")
            else:
                return await ctx.send(f"{current_name} shop doesn't exist!")

    @_rconshopset.command(name="additem")
    async def add_rcon_item(self, ctx, category, item_name, price=None):
        """
        Add an item to an rcon shop category

        Use quotes if item name has spaces
        """
        async with self.config.guild(ctx.guild).shops() as shops:
            # check if shop exists
            if category not in shops:
                return await ctx.send(f"{category} category not found!")
            # check if item exists
            if item_name in shops[category]:
                return await ctx.send(f"{item_name} item already exists!")
            if price:
                shops[category][item_name] = {"price": price, "options": {}, "paths": []}
                msg = await ctx.send(
                    "Type the full blueprint paths including quantity/quality/blueprint numbers below.\n"
                    "Separate each full path with a new line for multiple items in one pack.\n"
                    "Type `cancel` to cancel the item.")

                def check(message: discord.Message):
                    return message.author == ctx.author and message.channel == ctx.channel

                try:
                    reply = await self.bot.wait_for("message", timeout=240, check=check)
                    if reply.content.lower() == "cancel":
                        return await ctx.send("Item add canceled.")
                    if reply.attachments:
                        attachment_url = reply.attachments[0].url
                        async with aiohttp.ClientSession() as session:
                            async with session.get(attachment_url) as resp:
                                paths = await resp.text()
                                paths = paths.split("\r\n")
                    else:
                        paths = reply.content.split("\n")
                    shops[category][item_name]["paths"] = paths
                    return await ctx.send(f"Item paths set!")
                except asyncio.TimeoutError:
                    return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))
            else:
                shops[category][item_name] = {"price": False, "options": {}, "paths": []}
                return await ctx.send(f"Item added, please add options to it with `{ctx.prefix}shopset rcon addoption`")

    @_rconshopset.command(name="description")
    async def add_rcon_description(self, ctx, category, item_name, *, description: str):
        """Add a description to an RCON shop item"""
        async with self.config.guild(ctx.guild).shops() as shops:
            # check if shop exists
            if category not in shops:
                return await ctx.send(f"{category} category not found!")
                # check if item exists
            if item_name not in shops[category]:
                return await ctx.send(f"{item_name} item not found!")
            if "desc" in shops[category][item_name]:
                overwrite = "overwritten"
            else:
                overwrite = "set"
            shops[category][item_name]["desc"] = description
            await ctx.send(f"Description has been {overwrite} for {item_name} in the {category} category")

    @_rconshopset.command(name="delitem")
    async def delete_rcon_item(self, ctx, shop_name, item_name):
        """
        Delete an item from an rcon shop category
        """
        async with self.config.guild(ctx.guild).shops() as shops:
            # check if shop exists
            if shop_name not in shops:
                return await ctx.send(f"{shop_name} shop not found!")
            # check if item exists
            elif item_name not in shops[shop_name]:
                return await ctx.send(f"{item_name} item not found!")
            else:
                del shops[shop_name][item_name]
                return await ctx.tick()

    @_rconshopset.command(name="addoption")
    async def add_rcon_item_option(self, ctx, shop_name, item_name, option, price):
        """
        Add an option to an existing item in the rcon shop

        When it asks for paths, be sure to include the FULL blueprint path and <quantity> <quality> <BP T/F> identifiers
        for BP identifier: 1=True and 0=False
        """
        async with self.config.guild(ctx.guild).shops() as shops:
            # check if shop exists
            if shop_name not in shops:
                return await ctx.send(f"{shop_name} shop not found!")
            # check if item exists
            elif item_name not in shops[shop_name]:
                return await ctx.send(f"{item_name} item not found!")
            # check if option exists
            elif option in shops[shop_name][item_name]["options"]:
                return await ctx.send(f"{option} option already exists!")
            else:
                msg = await ctx.send(
                    "Type the full blueprint paths including quantity/quality/blueprint numbers below.\n"
                    "Separate each full path with a new line for multiple items in one option.\n"
                    "Type `cancel` to cancel the option.")

                def check(message: discord.Message):
                    return message.author == ctx.author and message.channel == ctx.channel

                try:
                    reply = await self.bot.wait_for("message", timeout=240, check=check)
                    if reply.content.lower() == "cancel":
                        return await ctx.send("Option add canceled.")
                    if reply.attachments:
                        attachment_url = reply.attachments[0].url
                        async with aiohttp.ClientSession() as session:
                            async with session.get(attachment_url) as resp:
                                paths = await resp.text()
                                paths = paths.split("\r\n")
                    else:
                        paths = reply.content.split("\n")
                    shops[shop_name][item_name]["options"][option] = {"price": price, "paths": paths}
                    return await ctx.send(f"Option set!")
                except asyncio.TimeoutError:
                    return await msg.edit("You took too long :yawning_face:")

    @_rconshopset.command(name="deloption")
    async def del_rcon_item_option(self, ctx, shop_name, item_name, option):
        """Delete an option from an existing item in the rcon shop"""
        async with self.config.guild(ctx.guild).shops() as shops:
            # check if shop exists
            if shop_name not in shops:
                return await ctx.send(f"{shop_name} shop not found!")
            # check if item exists
            elif item_name not in shops[shop_name]:
                return await ctx.send(f"{item_name} item not found!")
            # check if option exists
            elif option not in shops[shop_name][item_name]["options"]:
                return await ctx.send(f"{option} option not found!")
            else:
                del shops[shop_name][item_name]["options"][option]
                return await ctx.tick()

    @_rconshopset.command(name="checkitem")
    async def check_rcon_item(self, ctx, shop_name, item_name):
        """Check the blueprint strings in an item"""
        shops = await self.config.guild(ctx.guild).shops()
        # check if shop exists
        if shop_name not in shops:
            return await ctx.send(f"{shop_name} shop not found!")
        # check if item exists
        elif item_name not in shops[shop_name]:
            return await ctx.send(f"{item_name} item not found!")
        else:
            pathmsg = ""
            for path in shops[shop_name][item_name]["paths"]:
                pathmsg += f"`{path}`\n"
            return await ctx.send(pathmsg)

    # USER COMMANDS
    @commands.command(name="shopstats")
    async def shop_stats(self, ctx):
        """View all items purchased from all shops"""
        logs = await self.config.guild(ctx.guild).logs()
        if logs["items"] == {}:
            return await ctx.send("No logs yet!")
        pages = await shop_stats(logs)
        if await self.config.guild(ctx.guild).usebuttons():
            await buttonmenu(ctx, pages, DEFAULT_BUTTON_CONTROLS)
        else:
            await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="shoplb")
    async def shop_leaderboard(self, ctx):
        """Open the shop leaderboard"""
        logs = await self.config.guild(ctx.guild).logs()
        if logs["users"] == {}:
            return await ctx.send("No logs yet!")
        shop_logs = {}
        for user_id in logs["users"]:
            count = 0
            for item in logs["users"][user_id]:
                purchased = logs["users"][user_id][item]["count"]
                count += purchased
            shop_logs[user_id] = count
        sorted_items = sorted(shop_logs.items(), key=lambda x: x[1], reverse=True)
        pages = math.ceil(len(sorted_items) / 10)
        embeds = []
        start = 0
        stop = 10
        for page in range(int(pages)):
            if stop > len(sorted_items):
                stop = len(sorted_items)
            items = ""
            for i in range(start, stop, 1):
                user_id = int(sorted_items[i][0])
                member = self.bot.get_user(user_id)
                if not member:
                    try:
                        member = await self.bot.fetch_user(user_id)
                        member = member.name
                    except AttributeError:
                        member = await self.bot.get_user_info(user_id)
                        member = member.name
                    except discord.errors.NotFound:
                        member = "Unknown"
                else:
                    member = member.name
                purchases = sorted_items[i][1]
                items += f"**{member}**: `{purchases} purchases`\n"
            embed = discord.Embed(
                title="Item Purchases",
                description=items
            )
            embed.set_footer(text=f"Pages: {page + 1}/{pages}\n{random.choice(TIPS).format(p=ctx.prefix)}")
            embeds.append(embed)
            start += 10
            stop += 10
        pages = embeds
        if await self.config.guild(ctx.guild).usebuttons():
            await buttonmenu(ctx, pages, DEFAULT_BUTTON_CONTROLS)
        else:
            await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="playershopstats", aliases=["pss"])
    async def player_shop_stats(self, ctx, *, member: discord.Member = None):
        """Get a member's shop stats, or yours"""
        logs = await self.config.guild(ctx.guild).logs()
        users = await self.config.guild(ctx.guild).users()
        arktools = await self.arktools(ctx)
        if not arktools:
            return
        playerstats = await arktools.config.guild(ctx.guild).players()
        if logs["users"] == {}:
            return await ctx.send("No purchase history yet!")
        if not member:
            for user in logs["users"]:
                if str(ctx.author.id) == user:
                    member = ctx.author
                    break
            else:
                return await ctx.send("It appears you haven't purchased anything yet.")
        if str(member.id) not in logs["users"]:
            return await ctx.send("It appears that player hasn't purchased anything yet.")

        for xuid, stats in playerstats.items():
            if "discord" in stats:
                if str(member.id) == str(stats["discord"]):
                    gt = stats["username"]
                    break
        else:
            gt = "Unknown"
            xuid = "Unknown"

        embeds = []
        items = {}
        user = logs["users"][str(member.id)]
        for item, details in user.items():
            items[item] = details["count"]
        sorted_items = sorted(items.items(), key=lambda x: x[1], reverse=True)
        pages = math.ceil(len(sorted_items) / 5)
        start = 0
        stop = 5
        color = discord.Color.random()
        for p in range(pages):
            embed = discord.Embed(
                title=f"Shop stats for {member.display_name}",
                description=f"`Registered To: `{users[str(member.id)].upper()}\n"
                            f"`Player Name:   `{gt}\n"
                            f"`Player ID:     `{xuid}",
                color=color
            )
            if stop > len(sorted_items):
                stop = len(sorted_items)
            for i in range(start, stop, 1):
                item = sorted_items[i][0]
                amount = sorted_items[i][1]
                shop = user[item]["type"]
                embed.add_field(
                    name=item,
                    value=f"`Purchased: `{amount}\n"
                          f"`Shop Type: `{shop}",
                    inline=False
                )
            embed.set_footer(text=f"Pages {p + 1}/{pages}")
            start += 5
            stop += 5
            embeds.append(embed)
        if await self.config.guild(ctx.guild).usebuttons():
            await buttonmenu(ctx, embeds, DEFAULT_BUTTON_CONTROLS)
        else:
            await menu(ctx, embeds, DEFAULT_CONTROLS)

    @commands.command(name="rshop")
    @commands.guild_only()
    async def _rconshop(self, ctx):
        """
        Open up the rcon shop

        This shop uses RCON to send items directly to your inventory
        """
        # check if player is registered in arktools config and get their xuid if they are
        xuid = await self.get_xuid_from_arktools(ctx)
        if not xuid:
            return
        # check if player has set a cluster
        users = await self.config.guild(ctx.guild).users()
        if str(ctx.author.id) not in users:
            embed = discord.Embed(
                description=f"You need to set the cluster you play on.\n"
                            f"You can set it with `{ctx.prefix}setcluster`",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        await self.cat_compiler(ctx, "rcon")

    @commands.command(name="dshop")
    @commands.guild_only()
    async def _datashop(self, ctx):
        """
        Open up the data shop

        This shop uses pre-made data packs created in-game and then moved to a separate folder.

        The ark data, when purchased, gets copied to the cluster folder as the person's XUID, allowing
        them to access it as their own data.

        """

        # check if command was used in main server
        check = await self.config.main_server()
        if check != ctx.guild.id:
            embed = discord.Embed(
                title="Not Main Server",
                description="This feature can only be used on the main bot owner server!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # check if player is registered in arktools config and get their xuid if they are
        xuid = await self.get_xuid_from_arktools(ctx)
        if not xuid:
            return

        # check if player has set a cluster
        users = await self.config.guild(ctx.guild).users()
        if str(ctx.author.id) not in users:
            embed = discord.Embed(
                description=f"You need to set the cluster you play on.\n"
                            f"You can set it with `{ctx.prefix}setcluster`",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        await self.cat_compiler(ctx, "data")

    async def cat_compiler(self, ctx, shoptype: str, message: discord.Message = None):
        title, tip, categories = await self.get_types(ctx, shoptype)
        # how many categories
        category_count = len(categories.keys())
        # how many pages
        pages = math.ceil(category_count / 4)
        if category_count == 0:
            embed = discord.Embed(
                description="There are no categories added!",
                color=discord.Color.red()
            )
            if message:
                await self.clearall(ctx, message)
                return await message.edit(embed=embed)
            else:
                return await ctx.send(embed=embed)
        # category info setup
        shop_categories = []
        sorted_shops = sorted(categories, key=lambda x: x.lower())
        for category in sorted_shops:
            num_items = len(categories[category].keys())
            shop_categories.append((category, num_items))
        # sort that bitch
        shop_categories = sorted(shop_categories, key=lambda x: x[0])
        # menu setup
        start = 0
        stop = 4
        embedlist = []
        for page in range(int(pages)):
            embed = discord.Embed(
                title=title,
                description=f"Categories"
            )
            embed.set_thumbnail(url=SHOP_ICON)
            count = 0
            if stop > len(shop_categories):
                stop = len(shop_categories)
            for i in range(start, stop, 1):
                category_name = shop_categories[i][0]
                item_count = shop_categories[i][1]
                embed.add_field(
                    name=f"{SELECTORS[count]} {category_name}",
                    value=f"Items: {item_count}",
                    inline=False
                )
                count += 1
            embed.set_footer(text=f"Page {page + 1}/{pages}\n{tip}")
            embedlist.append(embed)
            start += 4
            stop += 4
        if await self.config.guild(ctx.guild).usebuttons():
            if message:
                await buttonmenu(ctx, embedlist, self.shop_button_controls, message)
            else:
                await buttonmenu(ctx, embedlist, self.shop_button_controls)
        else:
            if message:
                await menu(ctx, embedlist, self.shop_controls, message)
            else:
                await menu(ctx, embedlist, self.shop_controls)

    async def item_compiler(self, ctx, message, shoptype, category_name, altname=None, ):
        title, tip, categories = await self.get_types(ctx, shoptype)
        category = {}
        if altname:  # Category name is None, back button was pressed
            for cat in categories:
                for item in categories[cat]:
                    if altname == item:
                        category = categories[cat]
                        category_name = cat
                        break
        else:
            category = categories[category_name]
        # how many items
        item_count = len(category.keys())
        # how many pages
        pages = math.ceil(item_count / 4)
        if pages == 0:
            await self.clearall(ctx, message)
            embed = discord.Embed(
                description="Category has no items in it!",
                color=discord.Color.red()
            )
            return await message.edit(embed=embed)
        # item info setup
        items = []
        sorted_items = sorted(category, key=lambda x: x.lower())
        for item in sorted_items:
            num_options = len(category[item]["options"].keys())
            if num_options == 0:
                price = category[item]["price"]
            else:
                price = None
            items.append((item, num_options, price))
        # sort that bitch
        items = sorted(items, key=lambda x: x[0])
        # menu setup
        start = 0
        stop = 4
        embedlist = []
        for page in range(int(pages)):
            embed = discord.Embed(
                title=title,
                description=f"{category_name} items"
            )
            embed.set_thumbnail(url=SHOP_ICON)
            count = 0
            if stop > len(items):
                stop = len(items)
            for i in range(start, stop, 1):
                item_name = items[i][0]
                option_count = items[i][1]
                price = items[i][2]
                if option_count == 0:
                    embed.add_field(
                        name=f"{SELECTORS[count]} {item_name}",
                        value=f"Price: {price}",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=f"{SELECTORS[count]} {item_name}",
                        value=f"Options: {option_count}",
                        inline=False
                    )
                count += 1
            embed.set_footer(text=f"Page {page + 1}/{pages}\n{tip}")
            embedlist.append(embed)
            start += 4
            stop += 4
        if await self.config.guild(ctx.guild).usebuttons():
            await buttonmenu(ctx, embedlist, self.shop_button_controls, message)
        else:
            await menu(ctx, embedlist, self.shop_controls, message)

    # Either buy the item if it has no options, or compile the options and send back to menu
    async def buy_or_nah(self, ctx, message, name, shoptype):
        title, tip, categories = await self.get_types(ctx, shoptype)
        full_item = {}
        for category in categories:
            for item in categories[category]:
                if name == item:
                    full_item = categories[category][name]
                    break
        options = full_item["options"]
        price = full_item["price"]
        paths = None
        if shoptype == "rcon":
            paths = full_item["paths"]
        # if item has no options
        if price and not options:
            if "desc" in full_item:
                desc = full_item["desc"]
            else:
                desc = None
            await self.purchase(ctx, shoptype, name, name, price, message, desc, paths)
        # go back to menu if item contains options
        else:
            await self.op_compiler(ctx, message, name, shoptype)

    # Compile an items options and display in menu
    async def op_compiler(self, ctx, message, name, shoptype):
        title, tip, categories = await self.get_types(ctx, shoptype)
        full_item = {}
        for category in categories:
            for item in categories[category]:
                if name == item:
                    full_item = categories[category][name]
                    break
        options = full_item["options"]
        if "desc" in full_item:
            desc = full_item["desc"]
        else:
            desc = None
        # how many options
        option_count = len(options.keys())
        # how many pages
        pages = math.ceil(option_count / 4)
        # option info setup
        optionlist = []
        if shoptype == "rcon":
            for option, data in options.items():
                optionlist.append((option, data["price"]))
        else:
            for option, price in options.items():
                optionlist.append((option, price))
        # sort that bitch
        optionlist = sorted(optionlist, key=lambda x: x[0])
        # menu setup
        start = 0
        stop = 4
        embedlist = []
        for page in range(int(pages)):
            embed = discord.Embed(
                title=title,
                description=f"{name} options"
            )
            embed.set_thumbnail(url=SHOP_ICON)
            count = 0
            if stop > len(optionlist):
                stop = len(optionlist)
            for i in range(start, stop, 1):
                oname = optionlist[i][0]
                oprice = optionlist[i][1]
                embed.add_field(
                    name=f"{SELECTORS[count]} {oname}",
                    value=f"Price: {oprice}",
                    inline=False
                )
                count += 1
            if desc:
                embed.set_footer(text=f"{desc}\nPage {page + 1}/{pages}\n{tip}")
            else:
                embed.set_footer(text=f"Page {page + 1}/{pages}\n{tip}")
            embedlist.append(embed)
            start += 4
            stop += 4
        if await self.config.guild(ctx.guild).usebuttons():
            await buttonmenu(ctx, embedlist, self.shop_button_controls, message)
        else:
            await menu(ctx, embedlist, self.shop_controls, message)

    # Locate paths of rcon or data shop items for purchase
    async def pathfinder(self, ctx, message, shoptype, name, itemname=None):
        title, tip, categories = await self.get_types(ctx, shoptype)
        if shoptype == "rcon":
            for cname, cat in categories.items():
                for item, data in cat.items():
                    if item == itemname:
                        price = data["options"][name]["price"]
                        paths = data["options"][name]["paths"]
                        if "desc" in data:
                            desc = data["desc"]
                        else:
                            desc = None
                        return await self.purchase(
                            ctx,
                            shoptype,
                            name,
                            f"{itemname}({name})",
                            price,
                            message,
                            desc,
                            paths
                        )
        else:
            for cname, cat in categories.items():
                for item, data in cat.items():
                    for k, price in data["options"].items():
                        if k == name:
                            if "desc" in data:
                                desc = data["desc"]
                            else:
                                desc = None
                            return await self.purchase(
                                ctx,
                                shoptype,
                                name,
                                f"{itemname}({name})",
                                price,
                                message,
                                desc
                            )

    async def purchase(self, ctx, shoptype, filename, item_name, price, message, desc=None, paths=None):
        await self.clearall(ctx, message)
        users = await self.config.guild(ctx.guild).users()
        xuid = await self.get_xuid_from_arktools(ctx)
        currency_name = await bank.get_currency_name(ctx.guild)
        logchannel = await self.config.guild(ctx.guild).logchannel()
        logchannel = ctx.guild.get_channel(logchannel)
        usebuttons = await self.config.guild(ctx.guild).usebuttons()
        cname = users[str(ctx.author.id)]
        if not await bank.can_spend(ctx.author, int(price)):
            embed = discord.Embed(
                description=f"You don't have enough {currency_name} to buy this :smiling_face_with_tear:",
                color=discord.Color.red()
            )
            return await message.edit(embed=embed, components=[])

        def check(msg: discord.Message):
            return msg.author == ctx.author and msg.channel == ctx.channel

        # RCON shop purchase
        if shoptype == "rcon":
            # gather server data
            arktools = await self.arktools(ctx)
            if not arktools:
                return
            clusters = await arktools.config.guild(ctx.guild).clusters()
            if len(clusters.keys()) == 0:
                await message.delete()
                embed = discord.Embed(
                    description=f"There are no set clusters configured!",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed, components=[])
            if cname not in clusters:
                await message.delete()
                embed = discord.Embed(
                    description=f"Cluster no longer exists, please re-set your cluster with `{ctx.prefix}setcluster`",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed, components=[])

            # ASK FOR IMPLANT ID
            embed = discord.Embed(
                title="Type your Implant ID below",
                description=f"`Current cluster: ` **{cname}**",
                color=discord.Color.blue()
            )
            if desc:
                embed.set_footer(text=f"{desc}\n\nType 'cancel' to cancel the purchase.")
            else:
                embed.set_footer(text="Type 'cancel' to cancel the purchase.")
            embed.set_thumbnail(url="https://i.imgur.com/PZmR6QW.png")

            # See if player registered any implant ID's in-game
            implants = await self.get_implants_from_user(ctx, xuid)
            if implants and usebuttons:
                options = []
                for channel, implant in implants:
                    # Show any implant ID's that the player registered in-game for quicker checkout
                    op = SelectOption(f"{channel.name} - {implant}", f"{implant}-{channel.id}")
                    options.append(op)
                comp = SelectMenu(
                    custom_id=str(ctx.author.id),
                    placeholder="Or pick an existing implant from a map",
                    max_values=1,
                    options=options
                )
                try:
                    await message.edit(embed=embed, components=[comp])
                except discord.HTTPException:
                    log.warning("Error sending dropdown list with message, sending normal message instead")
                    await message.edit(embed=embed, components=[])
            else:
                await message.edit(embed=embed, components=[])

            def mcheck(inter):
                if inter.author != ctx.author:
                    asyncio.create_task(inter.reply("You are not the author of this command", ephemeral=True))
                return inter.author == ctx.author

            async def dropdown():
                select = await message.wait_for_dropdown(mcheck)
                res = {"inter": select}
                return res

            async def response():
                repl = await self.bot.wait_for("message", check=check)
                res = {"reply": repl}
                return res

            async def wait_first(*futures):
                # Thanks, Stack Overflow
                # https://stackoverflow.com/questions/31900244/select-first-result-from-two-coroutines-in-asyncio
                done, pending = await asyncio.wait(
                    futures,
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=80
                )
                # Bunch of stuff the example had that was giving "asyncio Task was destroyed but it is pending!"
                # gather = asyncio.gather(*pending)
                # print("cancelling")
                # gather.cancel()
                # print("gather.cancel()")
                # try:
                #     print("trying to gather")
                #     await gather
                #     print("cancelled gather")
                # except Exception as e:
                #     print(f"gather error: {str(e)}")
                #     pass
                if done:
                    # print(f"Done: {done}")
                    return done.pop().result()
                else:
                    await message.edit(
                        embed=discord.Embed(
                            description="Purchase cancelled",
                            color=discord.Color.dark_purple()
                        ),
                        components=[]
                    )
                    return None

            result = await wait_first(dropdown(), response())
            if not result:
                return
            if "inter" in result:
                inter = result["inter"]
                values = [option.value for option in inter.select_menu.selected_options]
                implant_id = values[0].split("-")[0]
                channel_id = values[0].split("-")[1]
                # Since they selected an option, we can just get the exact server instead of calling all of them
                # And since we have channel id we can bypass their set cluster
                # So it will still work if they are registered on one cluster and purchase something for another
                server = []
                for cluster_data in clusters.values():
                    for sname, server_data in cluster_data["servers"].items():
                        if str(server_data["chatchannel"]) == channel_id:
                            server.append((f"{sname} {cname}", server_data))
                if not server:
                    embed = discord.Embed(
                        description=f"Couldn't find server associated with channel ID {channel_id}"
                    )
                    return await message.edit(embed=embed, components=[])
                if implant_id:
                    return await self.sendoff_rcon_items(
                        ctx,
                        message,
                        server,
                        implant_id,
                        item_name,
                        paths,
                        price,
                        currency_name,
                        xuid,
                        logchannel
                    )
            else:
                reply = result["reply"]
                if "cancel" in reply.content.lower() or "no" in reply.content.lower():
                    embed = discord.Embed(
                        description=f"**Purchase cancelled.**\n",
                        color=discord.Color.blue()
                    )
                    embed.set_footer(text=random.choice(TIPS).format(p=ctx.prefix))
                    return await message.edit(embed=embed, components=[])

                resp = None
                if not reply.content.isdigit():  # Check if user is stupid
                    resp = "That is not a number. Include your implant ID NUMBER in the command, " \
                           "your Implant is in the top left of your inventory, look for the 'specimen' number"
                if len(reply.content) > 9 or len(reply.content) < 7:  # Check if user is blind
                    resp = "Incorrect ID, Implant ID's are 7 or 9 digits long, " \
                           "your Implant is in the top left of your inventory, look for the 'specimen' number"
                if resp:
                    embed = discord.Embed(
                        description=resp,
                        color=discord.Color.red()
                    )
                    return await message.edit(embed=embed, components=[])
                else:
                    embed = discord.Embed(
                        description="Sending items...",
                        color=discord.Color.orange()
                    )
                    embed.set_thumbnail(url=LOADING)
                    await message.edit(embed=embed, components=[])
                serverlist = []
                for sname, server_data in clusters[cname]["servers"].items():
                    serverlist.append((f"{sname} {cname}", server_data))
                return await self.sendoff_rcon_items(
                    ctx,
                    message,
                    serverlist,
                    reply.content,
                    item_name,
                    paths,
                    price,
                    currency_name,
                    xuid,
                    logchannel
                )

        # Data shop purchase
        else:
            clusters = await self.config.clusters()
            source_directory = await self.config.main_path()
            dest_directory = clusters[cname]
            # check source dir
            if not os.path.exists(source_directory):
                embed = discord.Embed(
                    description=f"Source path does not exist!",
                    color=discord.Color.red()
                )
                return await message.edit(embed=embed, components=[])
            # check destination dir
            if not os.path.exists(dest_directory):
                embed = discord.Embed(
                    description=f"Destination path does not exist!",
                    color=discord.Color.red()
                )
                return await message.edit(embed=embed, components=[])
            item_source_file = os.path.join(source_directory, filename)
            # check source file
            if not os.path.exists(item_source_file):
                embed = discord.Embed(
                    description=f"Data file does not exist!",
                    color=discord.Color.red()
                )
                return await message.edit(embed=embed, components=[])
            # last check to make sure user still wants to buy item
            embed = discord.Embed(
                description=f"**Are you sure you want to purchase the {item_name} item?**\n"
                            f"Type **yes** or **no**",
                color=discord.Color.blue()
            )
            if desc:
                embed.set_footer(text=desc)
            await message.edit(embed=embed, components=[])

            try:
                reply = await self.bot.wait_for("message", timeout=60, check=check)
            except asyncio.TimeoutError:
                return await message.edit(embed=discord.Embed(description="You took too long :yawning_face:"))

            if reply.content.lower() == "no" or reply.content.lower() == "cancel":
                embed = discord.Embed(
                    description=f"**Purchase cancelled.**\n",
                    color=discord.Color.blue()
                )
                embed.set_footer(text=random.choice(TIPS).format(p=ctx.prefix))
                return await message.edit(embed=embed, components=[])

            destination = os.path.join(dest_directory, xuid)
            # remove any existing data from destination
            if os.path.exists(destination):
                size = os.path.getsize(destination)
                # Check file size to see if player has anything in their ark data
                if int(size) > 0:
                    embed = discord.Embed(
                        title="Non-Empty File Detected!",
                        description=f"Transaction Cancelled, Empty your Ark Data first!",
                        color=discord.Color.red()
                    )
                    size = "{:,}".format(int(size))
                    embed.set_footer(text=f"Detected {size} bytes worth of ark data in your upload")
                    return await message.edit(embed=embed, components=[])
                try:
                    os.remove(destination)
                except PermissionError:
                    embed = discord.Embed(
                        description=f"Failed to clean source file!\n",
                        color=discord.Color.red()
                    )
                    return await message.edit(embed=embed, components=[])

            shutil.copyfile(item_source_file, destination)
            await bank.withdraw_credits(ctx.author, int(price))
            embed = discord.Embed(
                description=f"You have purchased the {item_name} item for {price} {currency_name}!\n"
                            f"**Make sure to wait 30 seconds before accessing your Ark data!**",
                color=discord.Color.green()
            )
            embed.set_footer(text=random.choice(TIPS).format(p=ctx.prefix))
            embed.set_thumbnail(url=SHOP_ICON)
            await message.edit(embed=embed, components=[])
            await self.log_purchase(ctx, shoptype, item_name, price, currency_name, xuid, logchannel, filename)

    async def sendoff_rcon_items(self,
                                 ctx,
                                 message,
                                 serverlist,
                                 implant_id,
                                 item_name,
                                 paths,
                                 price,
                                 currency_name,
                                 xuid,
                                 logchannel):
        def exe():
            results = {"success": [], "failed": []}
            for name, data in serverlist:
                try:
                    with Client(
                            host=data['ip'],
                            port=data['port'],
                            passwd=data['password'],
                            timeout=5
                    ) as client:
                        for path in paths:
                            client.run(f"giveitemtoplayer {implant_id} {path}")
                        client.close()
                        results["success"].append(name)
                except socket.timeout:
                    results["failed"].append(name)
                except Exception as e:
                    log.warning(f"Failed to send item to {name}\nError: {e}")
                    results["failed"].append(name)
            return results

        res = await self.bot.loop.run_in_executor(None, exe)

        if not res["success"]:  # If none of the commands were successful, don't deduct credits
            embed = discord.Embed(
                title="Purchase Failed",
                description="The servers timed out or lost connection during item send.\n"
                            "Please try again, if the problem persists, contact an admin.\n"
                            f"No {currency_name} has been deducted from your balance.",
                color=discord.Color.orange()
            )
            return await message.edit(embed=embed, components=[])

        # withdraw credits and send purchase message
        await bank.withdraw_credits(ctx.author, int(price))
        embed = discord.Embed(
            description=f"You have purchased the **{item_name}** item for **{price}** {currency_name}!\n"
                        f"Item was sent to ImplantID **{implant_id}**",
            color=discord.Color.green()
        )
        embed.set_footer(text=random.choice(TIPS).format(p=ctx.prefix))
        embed.set_thumbnail(url=SHOP_ICON)
        if res["failed"]:
            failed = ""
            for fail in res["failed"]:
                failed += f"{fail}\n"
            embed.add_field(
                name="Failed to send to some maps",
                value=box(failed),
                inline=False
            )
        await message.edit(embed=embed, components=[])
        await self.log_purchase(ctx, "rcon", item_name, price, currency_name, xuid, logchannel)

    async def log_purchase(self,
                           ctx,
                           shoptype,
                           item_name,
                           price,
                           currency_name,
                           xuid,
                           logchannel,
                           filename=None,
                           ):
        perms = None
        if logchannel:
            perms = logchannel.permissions_for(ctx.guild.me).send_messages
        # Add the purchase to logs
        if shoptype == "data":
            color = discord.Color.dark_teal()
        else:
            color = discord.Color.magenta()
        embed = discord.Embed(
            title=f"{shoptype.upper()} Purchase",
            description=f"**{ctx.author.name}** has purchased the {item_name} item.\n"
                        f"**Price:** {price} {currency_name}\n"
                        f"**XUID:** {xuid}",
            color=color
        )
        if perms and logchannel:
            await logchannel.send(embed=embed)
        async with self.config.guild(ctx.guild).logs() as logs:
            member = str(ctx.author.id)
            if shoptype == "data":
                item_name = filename
            # shop logs
            if item_name not in logs["items"]:
                logs["items"][item_name] = {"type": shoptype, "count": 1}
            else:
                logs["items"][item_name]["count"] += 1

            # individual user logs
            user = logs["users"].get(member)
            if not user:
                logs["users"][member] = {}

            item = logs["users"][member].get(item_name)
            if not item:
                logs["users"][member][item_name] = {"type": shoptype, "count": 1}

            else:
                logs["users"][member][item_name]["count"] += 1

    # MENU ITEMS
    async def select_one(
            self,
            ctx: commands.Context,
            pages: list,
            controls: dict,
            msg: discord.Message,
            page: int,
            timeout: float = None,
            emoji: str = None,
    ):
        buttons = False
        if "buttons" in controls:
            buttons = True
        if not buttons:
            await self.clear(ctx, msg, emoji, ctx.author)
        shoptype = pages[page].title.split()[0].lower().replace(" shop", "")
        level = pages[page].description
        if len(pages[page].fields) < 1:
            if buttons:
                return await buttonmenu(ctx, pages, controls, msg, page)
            return await menu(ctx, pages, controls, msg, page, timeout)
        name = pages[page].fields[0].name.split(' ', 1)[-1]
        await self.handler(ctx, msg, shoptype, level, name)

    async def select_two(
            self,
            ctx: commands.Context,
            pages: list,
            controls: dict,
            msg: discord.Message,
            page: int,
            timeout: float = None,
            emoji: str = None,
    ):
        buttons = False
        if "buttons" in controls:
            buttons = True
        if not buttons:
            await self.clear(ctx, msg, emoji, ctx.author)
        shoptype = pages[page].title.split()[0].lower().replace(" shop", "")
        level = pages[page].description
        if len(pages[page].fields) < 2:
            if buttons:
                return await buttonmenu(ctx, pages, controls, msg, page)
            return await menu(ctx, pages, controls, msg, page, timeout)
        name = pages[page].fields[1].name.split(' ', 1)[-1]
        await self.handler(ctx, msg, shoptype, level, name)

    async def select_three(
            self,
            ctx: commands.Context,
            pages: list,
            controls: dict,
            msg: discord.Message,
            page: int,
            timeout: float = None,
            emoji: str = None,
    ):
        buttons = False
        if "buttons" in controls:
            buttons = True
        if not buttons:
            await self.clear(ctx, msg, emoji, ctx.author)
        shoptype = pages[page].title.split()[0].lower().replace(" shop", "")
        level = pages[page].description
        if len(pages[page].fields) < 3:
            if buttons:
                return await buttonmenu(ctx, pages, controls, msg, page)
            return await menu(ctx, pages, controls, msg, page, timeout)
        name = pages[page].fields[2].name.split(' ', 1)[-1]
        await self.handler(ctx, msg, shoptype, level, name)

    async def select_four(
            self,
            ctx: commands.Context,
            pages: list,
            controls: dict,
            msg: discord.Message,
            page: int,
            timeout: float = None,
            emoji: str = None,
    ):
        buttons = False
        if "buttons" in controls:
            buttons = True
        if not buttons:
            await self.clear(ctx, msg, emoji, ctx.author)
        shoptype = pages[page].title.split()[0].lower().replace(" shop", "")
        level = pages[page].description
        if len(pages[page].fields) < 4:
            if buttons:
                return await buttonmenu(ctx, pages, controls, msg, page)
            return await menu(ctx, pages, controls, msg, page, timeout)
        name = pages[page].fields[3].name.split(' ', 1)[-1]
        await self.handler(ctx, msg, shoptype, level, name)

    async def go_back(
            self,
            ctx: commands.Context,
            pages: list,
            controls: dict,
            msg: discord.Message,
            page: int,
            timeout: float = None,
            emoji: str = None,
    ):
        buttons = False
        if "buttons" in controls:
            buttons = True
        if not buttons:
            await self.clear(ctx, msg, emoji, ctx.author)
        shoptype = pages[page].title.split()[0].lower().replace(" shop", "")
        level = pages[page].description
        await self.handler(ctx, msg, shoptype, level)

    async def handler(
            self,
            ctx: commands.Context,
            msg: discord.Message,
            shoptype: str,
            level: str,
            name: str = None,
    ):
        if level == "Categories":
            if name:
                await self.item_compiler(ctx, msg, shoptype, name)
            else:
                await self.cat_compiler(ctx, shoptype, msg)
        elif level.endswith("items"):
            if name:
                await self.buy_or_nah(ctx, msg, name, shoptype)
            else:
                await self.cat_compiler(ctx, shoptype, msg)
        elif level.endswith("options"):
            item = level.replace(" options", "")
            if name:
                await self.pathfinder(ctx, msg, shoptype, name, item)
            else:
                await self.item_compiler(ctx, msg, shoptype, None, item)
        else:
            log.warning(f"Menu handler borked in {ctx.guild.name}. shoptype: {shoptype}, level: {level}")
            return  # idk somethings fucked up, else case shouldnt happen
