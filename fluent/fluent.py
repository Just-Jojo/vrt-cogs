import discord
import googletrans
from redbot.core import commands, Config

translator = googletrans.Translator()


class Fluent(commands.Cog):
    """
    Seamless translation between two languages in one channel.

    Inspired by Obi-Wan3#0003's translation cog.
    """
    __author__ = "Vertyco"
    __version__ = "1.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=11701170)
        default_guild = {
            "channels": {}
        }
        self.config.register_guild(**default_guild)

    # Gets language identifier from string
    @staticmethod
    async def converter(language):
        for key, value in googletrans.LANGUAGES.items():
            if language == "chinese":
                language = "chinese (simplified)"
            if language == value:
                return key

    @staticmethod
    async def translator(msg, dest):
        translated_msg = translator.translate(msg, dest=str(dest))
        return translated_msg

    @commands.group()
    @commands.guildowner()
    async def fluent(self, ctx):
        """Base command"""
        pass

    @fluent.command()
    async def add(self, ctx, language1, language2, channel: discord.TextChannel = None):
        """
        Add a channel and languages to translate between

        Tip: Language 1 is the first to be converted. For example, if you expect most of the conversation to be
        in english, then make english language 2 to use less api calls.
        """
        if not channel:
            channel = ctx.channel
        language1 = await self.converter(language1.lower())
        language2 = await self.converter(language2.lower())
        if not language1 or not language2:
            return await ctx.send(f"One of the languages were not found: lang1-{language1} lang2-{language2}")
        async with self.config.guild(ctx.guild).channels() as channels:
            if channel.id in channels.keys():
                return await ctx.send(
                    embed=discord.Embed(description=f"❌ {channel.mention} is already a fluent channel."))
            else:
                channels[channel.id] = {
                    "lang1": language1,
                    "lang2": language2
                }
                color = discord.Color.green()
                return await ctx.send(embed=discord.Embed(description=f"✅ Fluent channel has been set!", color=color))

    @fluent.command()
    async def remove(self, ctx, channel: discord.TextChannel):
        """Remove a channel from Fluent"""
        async with self.config.guild(ctx.guild).channels() as channels:
            for channel_id in channels:
                if int(channel.id) == int(channel_id):
                    del channels[channel_id]
                    color = discord.Color.green()
                    await ctx.send(
                        embed=discord.Embed(description=f"✅ Fluent channel has deleted!", color=color))
                    break
            else:
                return await ctx.send(embed=discord.Embed(description=f"❌ {channel.mention} isn't a fluent channel."))

    @fluent.command()
    async def view(self, ctx):
        """View all fluent channels"""
        channels = await self.config.guild(ctx.guild).channels()
        embed = discord.Embed(
            title="Fluent Settings",
            description="Below is a list of fluent channels and their translated languages."
        )
        for channel in channels:
            discordchannel = ctx.guild.get_channel(int(channel))
            if discordchannel:
                lang1 = channels[channel]["lang1"]
                lang2 = channels[channel]["lang2"]
                embed.add_field(
                    name=discordchannel.name,
                    value=f"Channel ID: {discordchannel.id}\nFluent in: {lang1} <-> {lang2}"
                )
        return await ctx.send(embed=embed)

    @commands.Cog.listener("on_message")
    async def message_handler(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        channels = await self.config.guild(message.guild).channels()
        for channel_id in channels:
            if int(message.channel.id) == int(channel_id):
                lang1 = channels[channel_id]["lang1"]
                lang2 = channels[channel_id]["lang2"]
                channel = message.channel
                trans = await self.translator(message.content, lang1)
                if trans is None:
                    return await channel.send(embed=discord.Embed(description=f"❌ API seems to be down at the moment."))
                elif trans.src == lang2:
                    embed = discord.Embed(
                        description=f"{trans.text}"
                    )
                    if hasattr(message, "reply"):
                        return await message.reply(embed=embed, mention_author=False)
                elif trans.src == lang1:
                    trans = await self.translator(message.content, lang2)
                    embed = discord.Embed(
                        description=f"{trans.text}"
                    )
                    if hasattr(message, "reply"):
                        return await message.reply(embed=embed, mention_author=False)
                else:
                    return
