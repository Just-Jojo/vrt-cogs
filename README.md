# vrt-cogs
Various utility/fun cogs for Red V3.

I am relatively new to Python and coding in general, and enjoy working with API's and utility cogs for game servers. I plan on focusing in a niche of server management cogs but am keeping an open mind about any ideas that might interest me.

| Cog | Status | Description |
|---|:---:|---|
| ArkTools | ✓ | <details><summary>Remotely manage/monitor your Ark servers via RCON and chat seamlessly between in-game and discord.</summary> This cog comes packed with utility features for overseeing your Ark: Survival Evolved server; Including a status channel, join/leave logs, auto-renaming blacklisted player names, admin command logging with tribe logs, player stat tracking with leaderboards, and a sizeable collection of API tools for crossplay servers hosted from a Gamertag. (This cog is for self-hosted Xbox/PC crossplay or steam servers only, will not work with Nitrado)</details> |
| DayZTools | ✓ | <details><summary>Remotely manage/monitor your Nitrado Day-Z server from Discord.</summary> Various logging/management features for Day Z: Player join/leave log, server reboots, Killfeed and server status channel with server info.</details> |
| Inspire | ✓ | <details><summary>Get inpsirational messages.</summary> Super simple cog that replies to certain sad words with positive encouragements, and responds to the [p]inspire command with an inspirational quote using zenquotes.io API. Note: this cog was my very first project just to get the feel for Red so it's not very big and there aren't any plans of expanding it at the moment.</details>|
| MCTools | ✓ | <details><summary>Super simple status cog for Minecraft Bedrock servers.</summary> Displays a status embed showing server version and player count. Only for **Bedrock** dedicated servers since there is already one that supports Java.</details> |
| XTools | ✓ | <details><summary>View your Xbox profile, friends, screenshots and game clips using simple commands and interactive menus.</summary> Various tools for Xbox using xbl.io and xapi.us APIs.  (You will need to register for a free key to use this cog. The profile and friends command uses only xbl.io but the other commands use a combination of the two.)</details> |
| Fluent | ✓ | <details><summary>Set any channel as a two-way translator for fluent conversation.</summary> Set a channel and both languages, if a message is in language 1 it gets converted to language 2 and vice versa using googles free api.</details> |

# Installation
Run the following commands with your Red instance, replacing `[p]` with your prefix:

If you havent loaded the Downloader cog already, go ahead and do that first with: `[p]load downloader`. Then, 
```ini
[p]repo add vrt-cogs https://github.com/vertyco/vrt-cogs
[p]cog install vrt-cogs <list of cogs>
[p]load <list of cogs>
```

# Credits
- Obi-Wan3 for holding my hand through a lot of my issues and questions i've had while learning python, and providing me with the insight to find things by myself.
- The Red community as a whole for having dope cogs that I can creep on and see how they make stuff work.
- The Red discord coding channel for having lots of helpful cog creators!

# Contact
For support with my cogs, feel free to ping me in #support_othercogs in the [Red Cog Support](https://discord.gg/GET4DVk) server.

# Contributing
If you have any suggestions, or found any bugs, please let me know or [open an issue](https://github.com/vertyco/vrt-cogs/issues) on my repo!

If you would like to contribute, please talk to me on Discord first about your ideas before opening a PR.

# Feature Requests
I am open to any ideas or suggestions for new cogs/features!
