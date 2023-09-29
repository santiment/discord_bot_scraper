# discord_bot_scraper
This is the second version of discord scraper, which use server bot to scrape channels (realtime messages and history).
There is no user behaviour emulation and it doesn't act like a regular bot - you can't talk to it and it doesn't write messages itself.

**To create discord bot:**

1. Go to your personal account settings - `Advanced` tab
    1. turn on `Developer mode` in your Discord account
    2. click on `Discord API` link (it is located in the exact same line in blue)
    3. click on `DEVELOPER PORTAL` (left upper corner on newly opened page)
2. In the [Developer portal](https://discord.com/developers/applications), click on `Applications`. Log in again (if necessary) and then, back in the `Applications` menu, click on `New Application`
3. Name the bot and then click `Create`. 
4. Go to the `Bot` menu and generate a token using `Add Bot` or `Reset Token`. Copy and save this token straightaway. Also in this tab:
    1. enable `MESSAGE CONTENT INTENT` and `SERVER MEMBERS INTENT` options  
5. Click on `OAuth2` tab (from the left-side menu) and select `bot`:
    1. go to `Redirects` field  and click `Add Redirect` Set it to value `https://discord.com/api/oauth2/token`
    2. go to `URL Generator` and pick up `bot`, `guilds` and `messages.read` scopes ⇒ select redirect url `https://discord.com/api/oauth2/token` 
    3. set the permissions: `Read messages/View Channels` and `Read Message History`
    4. follow the `Generated link` to add bot to server ⇒ select your server to add your bot to it
6. Go back to Discord application and check permissions of the bot in Discord UI:
    1. Make sure to add bot explicitly to the channel (preferable): channel settings ⇒ `Permissions` ⇒ `Advanced permissions` ⇒`Roles/Members`) or to grant bot corresponding roles for access to necessary channels.
    2. extra actions for private channels: go to server settings ⇒ `Roles` tab and fix `View Channels` and `Read Message History` options if those are not enabled
    
**You have to be a server admin and/or you have an access to developer portal to be able to execute the steps above**

**Make sure to grant bot corresponding roles for access necessary channels in server settings**


> Additional extended guide with pictures: https://www.ionos.com/digitalguide/server/know-how/creating-discord-bot/
>
> Discord server permissions&roles explanation: https://www.youtube.com/watch?v=LSkPwZ0x6hc
>
> Developer portal link: https://discord.com/developers/applications



---
### Minimal required variables are:

`BOT_TOKEN` - the key variable to connect to the bot, could be found on Discord Developer portal, in `Bot` tab

`GUILD` - should be set to `<server_name>` to work with only one particular server

`CHANNELS` - the list of channel ids to collect messages from (str format `<channel1_id,channel2_id,...,channelN_id>`); channel id could be found in channel settings menu after enabling developer mode for your account

### Optional variables are:

`HISTORICAL_RUN_START_DATE` - retrieve messages after this date for the very first launch*. Datetime is considered to be specified in UTC timezone. Format `'%Y-%m-%dT%H:%M:%S'` is required.

***very first launch** means that there is no stored messages from this server in ES (fair for every new channel form the list as well). In case if ES index is empty and `HISTORICAL_RUN_START_DATE` doesn't set explicitly, the default history period is 1 day.

Every next launch will collect history starting the datetime of last message in Elasticsearch (regardless the channel).
