from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import box, pagify
from discord.ext import tasks
import functools
import discord
import datetime
import pytz
import unicodedata
import rcon
import asyncio
import os
import json
import re


class ArkTools(commands.Cog):
    """
    RCON tools and crosschat for Ark: Survival Evolved!
    """

    __author__ = "Vertyco"
    __version__ = "0.0.177"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 117117117, force_registration=True)
        default_guild = {
            "statuschannel": None,
            "statusmessage": None,
            "clusters": {},
            "servers": {},
            "servername": {},
            "ip": {},
            "port": {},
            "password": {},
            "chatchannel": {},
            "modroles": [],
            "modcommands": [],
            "fullaccessrole": None,
            "tribelogchannels": {},
            "apikeys": {},
            "crosschattoggle": False,
            "joinchannel": {},
            "leavechannel": {},
            "adminlogchannel": {},
            "globalchatchannel": {}
        }
        self.config.register_guild(**default_guild)

        self.chat_fromserver.start()

        self.rcontasks = []
        self.playerlist = {}

        """Windows event loop selector"""
        if os.name == 'nt':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    def cog_unload(self):
        self.chat_fromserver.cancel()



    # GROUPS
    @commands.group(name="arktools")
    @commands.guildowner()
    async def _setarktools(self, ctx: commands.Context):
        """Ark Tools base command."""
        pass

    @_setarktools.group(name="permissions")
    @commands.guildowner()
    async def _permissions(self, ctx: commands.Context):
        """Permission specific role settings for rcon commands."""
        pass

    @_setarktools.group(name="server")
    @commands.guildowner()
    async def _serversettings(self, ctx: commands.Context):
        """Server setup."""
        pass


    # PERMISSIONS COMMANDS
    @_permissions.command(name="setfullaccessrole")
    async def _setfullaccessrole(self, ctx: commands.Context, role: discord.Role):
        """Set a role you want to have full RCON access for."""
        await self.config.guild(ctx.guild).fullaccessrole.set(role.id)
        await ctx.send(f"Full rcon access role has been set to {role}")


    @_permissions.command(name="addmodrole")
    async def _addmodrole(self, ctx: commands.Context, *, role: discord.Role):
        """Add a role to allow limited command access for."""
        async with self.config.guild(ctx.guild).modroles() as modroles:
            if role.id in modroles:
                await ctx.send("That role already exists.")
            else:
                modroles.append(role.id)
                await ctx.send(f"The **{role}** role has been added.")

    @_permissions.command(name="delmodrole")
    async def _delmodrole(self, ctx: commands.Context, role: discord.Role):
        """Delete a mod role. use `[p]setarktools permissions view` to view current mod roles."""
        async with self.config.guild(ctx.guild).modroles() as modroles:
            if role.id in modroles:
                modroles.remove(role.id)
                await ctx.send(f"{role} role has been removed.")
            else:
                await ctx.send("That role isn't in the list.")


    @_permissions.command(name="addmodcommand")
    async def _addmodcommand(self, ctx: commands.Context, *, modcommand: str):
        """Add allowable commands for the mods to use."""
        async with self.config.guild(ctx.guild).modcommands() as modcommands:
            if modcommand in modcommands:
                await ctx.send("That command already exists!")
            else:
                modcommands.append(modcommand)
                await ctx.send(f"The command **{modcommand}** has been added to the list.")

    @_permissions.command(name="delmodcommand")
    async def _delmodcommand(self, ctx: commands.Context, modcommand: str):
        """Delete an allowed mod command."""
        async with self.config.guild(ctx.guild).modcommands() as modcommands:
            if modcommand in modcommands:
                modcommands.remove(modcommand)
                await ctx.send(f"The {modcommand} command has been removed.")
            else:
                await ctx.send("That command doesnt exist")


    # SERVER SETTINGS COMMANDS
    @_serversettings.command(name="addcluster")
    async def _addcluster(self, ctx: commands.Context,
                          clustername: str,
                          joinchannel: discord.TextChannel,
                          leavechannel: discord.TextChannel,
                          adminlogchannel: discord.TextChannel,
                          globalchatchannel: discord.TextChannel):
        """Add a cluster with specified log channels."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername in clusters.keys():
                await ctx.send("Cluster already exists")
            else:
                clusters[clustername] = {
                    "joinchannel": joinchannel.id,
                    "leavechannel": leavechannel.id,
                    "adminlogchannel": adminlogchannel.id,
                    "globalchatchannel": globalchatchannel.id,
                    "servers": {}
                }
                await ctx.send(f"**{clustername}** has been added to the list of clusters.")

    @_serversettings.command(name="delcluster")
    async def _delcluster(self, ctx: commands.Context, clustername: str):
        """Delete a cluster."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername not in clusters.keys():
                await ctx.send("Cluster name not found")
            else:
                del clusters[clustername]
                await ctx.send(f"{clustername} cluster has been deleted")


    @_serversettings.command(name="addserver")
    async def _addserver(self, ctx: commands.Context, clustername: str, servername: str, ip: str,
                         port: int, password: str, channel: discord.TextChannel):
        """Add a server."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername in clusters.keys():
                if servername in clusters[clustername]["servers"].keys():
                    await ctx.send(f"The **{servername}** server was **overwritten** in the **{clustername}** cluster!")
                if servername not in clusters[clustername]["servers"].keys():
                    await ctx.send(f"The **{servername}** server has been added to the **{clustername}** cluster!")
            clusters[clustername]["servers"][servername] = {
                "name": servername,
                "ip": ip,
                "port": port,
                "password": password,
                "chatchannel": channel.id
            }
            if clustername not in clusters.keys():
                await ctx.send(f"The cluster {clustername} does not exist!")

    @_serversettings.command(name="delserver")
    async def _delserver(self, ctx: commands.Context, clustername: str, servername: str):
        """Remove a server."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            server = clusters[clustername]["servers"]
            if servername in server.keys():
                del clusters[clustername]["servers"][servername]
                await ctx.send(f"{servername} server has been removed from {clustername}")
            else:
                await ctx.send(f"{servername} server not found.")

    @_serversettings.command(name="setstatuschannel")
    async def _setstatuschannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set a channel for a server status embed."""
        await self.config.guild(ctx.guild).statuschannel.set(channel.id)
        await ctx.send(f"Status channel has been set to {channel.mention}")

    # VIEW SETTINGSs
    @_permissions.command(name="view")
    async def _viewperms(self, ctx: commands.Context):
        """View current permission settings."""

        settings = await self.config.guild(ctx.guild).all()
        color = discord.Color.dark_purple()
        embed = discord.Embed(
            title=f"Permission Settings",
            color=color,
            description=f"**Full Access Role:** {settings['fullaccessrole']}\n"
                        f"**Mod Roles:** {settings['modroles']}\n"
                        f"**Mod Commands:** {settings['modcommands']}\n"
                        f"**Status Channel:** 'Work in progress'"
        )
        return await ctx.send(embed=embed)

    @_serversettings.command(name="view")
    async def _viewsettings(self, ctx: commands.Context):
        """View current server settings."""
        settings = await self.config.guild(ctx.guild).all()
        serversettings = ""
        for pv in settings["clusters"]:
            serversettings += f"**{pv.upper()} Cluster**\n"
            for k, v in settings["clusters"][pv].items():
                if k == "globalchatchannel":
                    serversettings += f"`GlobalChat:` {ctx.guild.get_channel(v).mention}\n"
                if k == "adminlogchannel":
                    serversettings += f"`AdminLog:` {ctx.guild.get_channel(v).mention}\n"
                if k == "joinchannel":
                    serversettings += f"`JoinChannel:` {ctx.guild.get_channel(v).mention}\n"
                if k == "leavechannel":
                    serversettings += f"`LeaveChannel:` {ctx.guild.get_channel(v).mention}\n"
                else:
                    continue
            for server in settings["clusters"][pv]["servers"]:
                for k, v in settings["clusters"][pv]["servers"][server].items():
                    if k == "name":
                        serversettings += f"**Map:** `{v.capitalize()}`\n"
                    if k != "chatchannel":
                        if k != "name":
                            if k != "ip":
                                serversettings += f"**{k.capitalize()}:** `{v}`\n"
                            if k == "ip":
                                serversettings += f"**{k.upper()}:** `{v}`\n"
                    if k == "chatchannel":
                        serversettings += f"**Channel:** {ctx.guild.get_channel(v).mention}\n"
                serversettings += "\n"

        color = discord.Color.dark_purple()
        embed = discord.Embed(
            title=f"**Server Settings**",
            color=color,
            description=f"{serversettings}"
        )
        await ctx.send(embed=embed)


    #####################################################################RCON
    @_setarktools.command(name="rcon")
    async def rcon(self, ctx: commands.Context, clustername: str, servername: str, *, command: str):
        """Perform an RCON command."""
        settings = await self.config.guild(ctx.guild).all()

        # Check whether user has perms
        userallowed = False
        for role in ctx.author.roles:
            if str(role.id) in settings['modroles']:
                userallowed = True
            elif str(role.id) in settings['modroles']:
                modcmds = settings['modcommands'].values()
                if command.lower() in [x.lower() for x in modcmds]:
                    userallowed = True
        if not userallowed and not ctx.guild.owner == ctx.author:
            return await ctx.send("You do not have the required permissions to run that command.")

        # data setup logic to send commands to task loop
        serverlist = []
        if clustername != "all":
            if clustername not in settings["clusters"]:
                return await ctx.send("Cluster name not found.")
            if servername == "all":
                for server in settings["clusters"][clustername]["servers"]:
                    serverlist.append(settings["clusters"][clustername]["servers"][server])
            if servername != "all":
                if servername not in settings["clusters"][clustername]["servers"]:
                    return await ctx.send("Server name not found.")
                serverlist.append(settings["clusters"][clustername]["servers"][servername])
        if clustername == "all":
            for cluster in settings["clusters"]:
                if servername == "all":
                    for server in settings["clusters"][cluster]["servers"]:
                        settings["clusters"][cluster]["servers"][server]["cluster"] = cluster
                        serverlist.append(settings["clusters"][cluster]["servers"][server])
                if servername != "all":
                    if servername not in settings["clusters"][cluster]["servers"]:
                        return await ctx.send("Server name not found.")
                    serverlist.append(settings["clusters"][cluster]["servers"][servername])

        # sending off to the task loop
        try:
            tasks = []
            for server in serverlist:
                tasks.append(self.manual_rcon(server, command, ctx))
            await asyncio.gather(*tasks)
        except WindowsError as e:
            if e.winerror == 121:
                await ctx.send(f"The **{server['name']}** **{cluster} server has timed out and is probably down.")
        await ctx.send(f"Executed `{command}` command on `{len(serverlist)}` servers for `{clustername}` clusters.")

    # RCON manual command logic
    async def manual_rcon(self, serverlist, command, ctx):
        res = await rcon.asyncio.rcon(
        command=command,
        host=serverlist['ip'],
        port=serverlist['port'],
        passwd=serverlist['password']
        )
        res = res.rstrip()
        if command.lower() == "listplayers":
            await ctx.send(f"**{serverlist['name'].capitalize()} {serverlist['cluster'].upper()}**\n"
                           f"{box(res, lang='python')}")

        else:
            await ctx.send(box(res, lang="python"))

    # Message listener to send chat to designated servers
    @commands.Cog.listener("on_message")
    async def chat_toserver(self, message: discord.Message):
        if message.author.bot:
            return
        if message.mentions:
            for mention in message.mentions:
                message.content = message.content.replace(f"<@!{mention.id}>",
                                                          "@"+str(mention.name)).replace(f"<@{mention.id}>",
                                                                                         "@"+str(mention.name))
        if message.channel_mentions:
            for mention in message.channel_mentions:
                message.content = message.content.replace(f"<#{mention.id}>", f"#{mention.name}")
        if message.role_mentions:
            for mention in message.role_mentions:
                message.content = message.content.replace(f"<@&{mention.id}>", f"@{mention.name}")

        # Check if message was sent in global chat channel.
        clusterchannels, allservers = await self.globalchannelchecker(message.channel)

        # Check if message was sent in a map channel.
        chatchannels, map = await self.mapchannelchecker(message.channel)

        if message.channel.id in clusterchannels:
            await self.chat_toserver_rcon(allservers, message)
        if message.channel.id in chatchannels:
            await self.chat_toserver_rcon(map, message)

    async def chat_toserver_rcon(self, server, message):
        for data in server:
            normalizedname = unicodedata.normalize('NFKD', message.author.name).encode('ascii', 'ignore').decode()
            await rcon.asyncio.rcon(
                command=f"serverchat {normalizedname}: {message.content}",
                host=data['ip'],
                port=data['port'],
                passwd=data['password']
            )

    async def globalchannelchecker(self, channel):
        settings = await self.config.guild(channel.guild).all()
        clusterchannels = []
        allservers = []
        for cluster in settings["clusters"]:
            if settings["clusters"][cluster]["globalchatchannel"] == channel.id:
                clusterchannels.append(settings["clusters"][cluster]["globalchatchannel"])
                for server in settings["clusters"][cluster]["servers"]:
                    clusterchannels.append(settings["clusters"][cluster]["servers"][server]["chatchannel"])
                    allservers.append(settings["clusters"][cluster]["servers"][server])
        return clusterchannels, allservers

    async def mapchannelchecker(self, channel):
        settings = await self.config.guild(channel.guild).all()
        chatchannels = []
        map = []
        for cluster in settings["clusters"]:
            for server in settings["clusters"][cluster]["servers"]:
                if settings["clusters"][cluster]["servers"][server]["chatchannel"] == channel.id:
                    chatchannels.append(settings["clusters"][cluster]["servers"][server]["chatchannel"])
                    map.append(settings["clusters"][cluster]["servers"][server])
        return chatchannels, map

    # Crosschat loop logic
    @tasks.loop(seconds=8, reconnect=True)
    async def chat_fromserver(self):
        config = await self.config.all_guilds()
        for guildID in config:
            guild = self.bot.get_guild(guildID)
            if not guild:
                continue
            guildsettings = await self.config.guild(guild).clusters()
            if not guildsettings:
                continue
            for cluster in guildsettings:
                if not guildsettings[cluster]:
                    continue
                globalchatchannel = guildsettings[cluster]["globalchatchannel"]
                adminlogchannel = guildsettings[cluster]["adminlogchannel"]
                for server in guildsettings[cluster]["servers"]:
                    guildsettings[cluster]["servers"][server]["adminlogchannel"] = adminlogchannel
                    guildsettings[cluster]["servers"][server]["globalchatchannel"] = globalchatchannel
                    guildsettings[cluster]["servers"][server]["cluster"] = cluster
                    server = guildsettings[cluster]["servers"][server]

                    try:
                        res = await self.bot.loop.run_in_executor(None, lambda: self.rconloop("getchat", server))
                        await self.bot.loop.run_in_executor(None, lambda: self.messagehandler(guild, server, res))
                    except Exception as e:
                        print(f"Main loop failure: {e}")

    async def rconloop(self, command, server):
        try:
            res = await rcon.asyncio.rcon(
                command=command,
                host=server['ip'],
                port=server['port'],
                passwd=server['password']
            )
            return res
        except Exception as e:
            print(f"RCON loop failure: {e}")

    async def messagehandler(self, guild, server, res):
        adminlog = guild.get_channel(server["adminlogchannel"])
        globalchat = guild.get_channel(server["globalchatchannel"])
        chatchannel = guild.get_channel(server["chatchannel"])
        if "Server received, But no response!!" in res:
            return
        msgs = res.split("\n")
        messages = []
        for msg in msgs:
            if msg.startswith("AdminCmd:"):
                adminmsg = msg
                await adminlog.send(f"**{server['name'].capitalize()}**\n{box(adminmsg, lang='python')}")
            if "): " not in msg:
                continue
            if "tribe" and ", ID" in msg.lower():
                continue
            else:
                if 'Server received, But no response!!' not in msg:
                    if not msg.startswith('SERVER:'):
                        messages.append(msg)
        for msg in messages:
            await chatchannel.send(msg)
            await asyncio.sleep(0.1)
            await globalchat.send(f"{chatchannel.mention}: {msg}")

    @chat_fromserver.before_loop
    async def before_chat_fromserver(self):
        await self.bot.wait_until_red_ready()
        print("Crosschat loop is ready.")



    @commands.command(name="test")
    async def mytestcom(self, ctx):
        config = await self.config.all_guilds()
        for guildID in config:
            guild = self.bot.get_guild(guildID)
            if not guild:
                continue
            guildsettings = await self.config.guild(guild).clusters()
            if not guildsettings:
                continue
            for cluster in guildsettings:
                globalchatchannel = guildsettings[cluster]["globalchatchannel"]
                for server in guildsettings[cluster]["servers"]:
                    guildsettings[cluster]["servers"][server]["globalchatchannel"] = globalchatchannel
                    guildsettings[cluster]["servers"][server]["cluster"] = cluster



                    await ctx.send(guildsettings[cluster]["servers"][server])


