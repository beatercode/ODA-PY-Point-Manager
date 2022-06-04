# bot.py
import os
import json
import discord
import re
# from dotenv import load_dotenv#
from discord.ext import commands#, tasks
import numpy as np
import datetime
from dateutil.relativedelta import relativedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import logging


def read_json(name='users.json'):
    with open(name, 'r') as f:
        return json.load(f)


def write_json(file, name='users.json'):
    with open(name, 'w') as f:
        json.dump(file, f)


def create_dict_index(d, meta_list):
    for i in range(len(meta_list)):
        d[meta_list[i]] = i


def str2datetime(dt, format="%Y-%m-%d %H:%M:%S"):
    return datetime.datetime.strptime(dt, format)


def datetime2str(dt, format="%Y-%m-%d %H:%M:%S"):
    return dt.strftime(format=format)
  

logging.basicConfig(filename='OdaClanPointsLOG.log', level=logging.WARNING)
now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
logging.warning('Started at ' +  datetime2str(now))

meta = read_json('meta.json')
invites = {}
users = read_json('users.json')
data_backup = read_json('data_backup.json')
users_list_guild = list(users.keys())
# load_dotenv(r"C:\Users\BertFede\Documents\zBack-up hard disk\Varie\ODA Clan Points Bot\OdaBot.env")
GUILD = os.environ['ODAClanPointsGUILD']
TOKEN = os.environ['ODAClanPointsTOKEN']
# TOKEN = os.getenv('DISCORD_TOKEN', "Token does not exist")
# GUILD = os.getenv('DISCORD_GUILD', "Guild does not exist")
# DIRECTORY = os.getenv('ACTUAL_DIRECTORY', "Directory does not exist")

role_oda_clan_id = meta['role_oda_clan_id']
role_oda_clan = meta['role_oda_clan']
role_oda_clan_lvl = meta['role_oda_clan_lvl']
role_oda_clan_color = meta['role_oda_clan_color']  # add the code of all colors of role names
role_oda_clan_command = meta['role_oda_clan_command']
role_oda_clan_percentage = meta['role_oda_clan_percentage']
# [percentage of upgrades, percentage of remain] -> 100 - percentage of remain = percentage of downgrade
role_oda_clan_discount = meta['role_oda_clan_discount']  # discounts of first 3 positions for each role
texts_delimiters = meta['texts_delimiters']
texts_delimiters_re = meta['texts_delimiters_re']
cmd_list = meta['cmd_list']

dict_index_roles = {}
create_dict_index(dict_index_roles, role_oda_clan_id)
create_dict_index(dict_index_roles, role_oda_clan_command)

points_daily_per_role = meta['points_daily_per_role']  # 150, 120, 100, 100
points_survey_per_role = meta['points_survey_per_role']
points_reaction_per_role = meta['points_reaction_per_role']
points_invitation_per_role = meta['points_invitation_per_role']

ch_list_reactions = meta['ch_list_reactions']  # channels where the reactions give points
ch_list_commands = meta['ch_list_commands']  # channels where the bot commands can be used
ch_commands_daimyo = meta['ch_commands_daimyo']  # channels where the bot commands can be used by Daimyo
ch_commands_tenno = meta['ch_commands_tenno']  # channels where the bot commands can be used by Tenno
ch_list_surveys = meta['ch_list_surveys']  # channel for the server surveys
ch_announcements = meta['ch_announcements']  # channels where the announcement to the server are done
ch_feedback = meta['ch_feedback']  # channels where the bot gives us feedbacks (only daimyo and tenno)

intents = discord.Intents.default()
intents.members = True
intents.reactions = True

client = commands.Bot(command_prefix='oda.', intents=intents)
# os.chdir(DIRECTORY)


@client.event
async def on_ready():
    # guild = discord.utils.find(lambda g: g.name == GUILD, client.guilds)
    guild = discord.utils.get(client.guilds, name=GUILD)
    print(
        f'{client.user} is connected to the following guild:\n'
        f'{guild.name}(id: {guild.id})'
    )

    for guild in client.guilds:
        # Adding each guild's invites to our dict
        invites[guild.id] = await guild.invites()

    await check_users_on_ready()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(hourly_backup, CronTrigger(minute=0, second=0, timezone='UTC'))
    # scheduler.add_job(hourly_backup, CronTrigger(minute=10, second=0, timezone='UTC'))
    scheduler.add_job(hourly_backup, CronTrigger(minute=20, second=0, timezone='UTC'))
    scheduler.add_job(hourly_backup, CronTrigger(minute=30, second=0, timezone='UTC'))
    scheduler.add_job(hourly_backup, CronTrigger(minute=40, second=0, timezone='UTC'))
    scheduler.add_job(hourly_backup, CronTrigger(minute=50, second=0, timezone='UTC'))
    scheduler.add_job(hourly_backup_users, CronTrigger(minute=10, second=0, timezone='UTC'))
    scheduler.add_job(check_name_oda, CronTrigger(minute=55, second=0, timezone='UTC'))
    scheduler.add_job(day_reset, CronTrigger(hour=0, minute=0, second=30, timezone='UTC'))
    # scheduler.add_job(day_reset, CronTrigger(day=2, hour=8, minute=1, second=10, timezone='UTC'))
    scheduler.add_job(daily_print, CronTrigger(hour=0, minute=5, second=0, timezone='UTC'))
    scheduler.add_job(monthly_podium_prices, CronTrigger(day=1, hour=0, minute=2, second=0, timezone='UTC'))
    scheduler.add_job(monthly_upgrade_roles, CronTrigger(day=1, hour=0, minute=3, second=0, timezone='UTC'))
    scheduler.add_job(month_reset, CronTrigger(day=1, hour=0, minute=5, second=0, timezone='UTC'))
    scheduler.start()


@client.event
async def on_raw_reaction_add(payload):
    await reactions_up_points(payload)
    await reactions_surveys_up_points(payload)


@client.event
async def on_raw_reaction_remove(payload):
    await reactions_down_points(payload)
    await reactions_surveys_down_points(payload)


@client.event
async def on_member_join(member):
    # Getting the invites before the user joining from our cache for this specific guild
    invites_before_join = invites[member.guild.id]

    # Getting the invites after the user joining, so we can compare it with the first one, and
    # see which invite uses number increased
    invites_after_join = await member.guild.invites()
    inviter_id = None
    # Loops for each invite we have for the guild the user joined.
    for invite in invites_before_join:
        # Now, we're using the function we created just before to check which invite count is bigger
        # than it was before the user joined.
        if invite is not None:
            find_invite = find_invite_by_code(invites_after_join, invite.code)
            if find_invite is not None:
                if invite.uses < find_invite.uses:
                    # Now that we found which link was used, we will print a couple of things in our console:
                    # the name, invite code used the person who created the invite code, or the inviter.

                    inviter_id = str(invite.inviter.id)

                    # We will now update our cache, so it's ready
                    # for the next user that joins the guild
                    invites[member.guild.id] = invites_after_join

                    # We break here since we already found which one was used and there is no point in
                    # looping when we already got what we wanted
                    break
    await update_data(member, inviter_id, is_new_member=True, up_role_ds=False)
    welcome_msg = "Welcome to <@" + str(member.id) + ">, a new member of the Oda Clan!"
    channel = client.get_channel(ch_feedback)
    await channel.send(welcome_msg)


@client.event
async def on_member_remove(member):
    # Updates the cache when a user leaves to make sure
    # everything is up to date

    user_id = str(member.id)
    inviter_id = users[user_id]["invited_by"][0]
    inviter_points = users[user_id]["invited_by"][1]

    if inviter_id is not None:
        update_point(inviter_id, -inviter_points)
        update_data_backup(p=-inviter_points, cat='a')

    invites[member.guild.id] = await member.guild.invites()


@client.event
async def on_member_update(before, after):
    await member_update_role(after, after.roles)


@client.event
async def on_message(message):
    if message.author == client.user or message.author.bot:
        return

    if message.channel.id in ch_list_commands:
        await cmd_acc(message)
        await cmd_leaderboard(message)
        await cmd_give(message)
        await cmd_daily(message)

    if message.channel.id == ch_commands_daimyo or message.channel.id == ch_commands_tenno:
        await cmd_up_role(message)
        await cmd_up_point(message)
        await cmd_backup(message)

    if message.channel.id == ch_commands_tenno:
        await cmd_leader_up_role(message)


async def member_update_role(user, roles):
    highest_role = None
    for role in roles:
        if role.id in role_oda_clan_id:
            highest_role = role.id
    if highest_role is not None:
        if str(user.id) in users.keys():
            if highest_role != users[str(user.id)]['role_id']:
                await update_role(user, role_oda_clan_id.index(highest_role), up_role_ds=False)
        else:
            print('member update but not present in the json ' + str(user.id))


async def day_reset():
    await client.wait_until_ready()
    c = client.get_channel(ch_feedback)  # ch bot announcement? or delete

    new_multiplier = 1  # it becomes 1.1 when we add this feature in the game

    for user_id in users.keys():
        if not users[user_id]['daily']:
            users[user_id]['consecutive_daily'] = 0
        else:
            users[user_id]['daily'] = False

        if not users[user_id]['oda_in_name']:
            users[user_id]['oda_in_name'] = True
            users[user_id]['consecutive_oda'] = 0
        else:
            users[user_id]['multiplier'] = new_multiplier
            users[user_id]['consecutive_oda'] += 1

    await c.send("Daily and Oda in name resets done")  # ch bot announcement? or delete


async def hourly_backup():
    await client.wait_until_ready()
    c = client.get_channel(ch_feedback)  # ch bot announcement? or delete

    if len(users) == 0:
        await c.send("users is empty <@546111431347666967> <@202500951230119936>")
        return
    if len(data_backup) == 0:
        await c.send("data_backup is empty <@546111431347666967> <@202500951230119936>")
        return

    write_json(users)
    write_json(data_backup, name='data_backup.json')

    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    now_str = datetime2str(now)

    await c.send("Hourly backup of users.json and data_backup.json " + now_str)  # ch bot announcement? or delete


async def hourly_backup_users():
    await client.wait_until_ready()
    c = client.get_channel(ch_feedback)  # ch bot announcement? or delete

    if len(users) == 0:
        await c.send("users is empty <@546111431347666967> <@202500951230119936>")
        return

    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    now_str = datetime2str(now)
    h = str(now.hour)
    name_backup = "users_backup_" + h + ".json"
    write_json(users, name=name_backup)

    users_backup_date = read_json("users_backup_date.json")
    users_backup_date[h] = now_str
    write_json(users_backup_date, name='users_backup_date.json')

    await c.send("Hourly backup of " + name_backup + " " + now_str)  # ch bot announcement? or delete


async def check_users_on_ready():
    c = client.get_channel(ch_feedback)  # ch bot announcement? or delete

    guild = discord.utils.get(client.guilds, name=GUILD)
    users_keys = list(users.keys())
    for member in guild.members:
        if not member.bot:
            if str(member.id) not in users_keys:
                print('New members ', member.id, member.name)
                await update_data(member, up_role_ds=False)
            else:
                list_index_role = await list_role_user_index(member)
                if list_index_role:
                    if list_index_role[-1] != role_oda_clan_id.index(users[str(member.id)]['role_id']):
                        await update_role(member, list_index_role[-1], up_role_ds=False)
                        # print('manually modified when bot switch off ', member.id, member.name, list_index_role[-1], list_index_role)
                    # else:
                    #     print('all right ', member.id, member.name)

    await c.send("Check users on ready: all id present. At " + datetime2str(now))  # ch bot announcement? or delete


async def list_role_user_index(user):
    actual_role_index = []
    for i in range(len(role_oda_clan_id)):
        tmp_role_id = role_oda_clan_id[i]
        tmp = discord.utils.get(user.roles, id=tmp_role_id)
        if tmp is not None:
            actual_role_index.append(i)
    return actual_role_index


async def cmd_backup(message):
    if message.content.startswith('oda.backup'):
        c = client.get_channel(ch_feedback)  # ch bot announcement? or delete

        user = message.author
        id_user = str(user.id)
        role_author_id = users[id_user]['role_id']
        index_role_author = role_oda_clan_id.index(role_author_id)
        if index_role_author < 8:
            return

        if len(users) == 0:
            await c.send("users is empty <@546111431347666967> <@202500951230119936>")
            return
        if len(data_backup) == 0:
            await c.send("data_backup is empty <@546111431347666967> <@202500951230119936>")
            return

        write_json(users)
        write_json(data_backup, name='data_backup.json')

        await c.send("Backup of users.json and data_backup.json done")  # ch bot announcement? or delete


async def month_reset():
    await client.wait_until_ready()
    c = client.get_channel(ch_feedback)  # ch bot announcement? or delete

    for user_id in users.keys():
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        last_month = now + relativedelta(months=-1)
        users[user_id]['backup_invitation'].append([datetime2str(last_month, '%Y/%m'),
                                                    users[user_id]['monthly_invitation']])
        users[user_id]['monthly_invitation'] = 0
        users[user_id]['monthly_give_limit'] = 5000

    await c.send("Monthly backup done")  # ch bot announcement? or delete


async def daily_print():
    await client.wait_until_ready()
    channel = client.get_channel(ch_feedback)  # ch bot announcement? or delete

    index_to_print = dict_index_roles["noka"]
    to_print = role_oda_clan[index_to_print] + " invite list: \n"
    for user in users.keys():
        if users[user]['role_id'] == role_oda_clan_id[index_to_print]:
            to_print += "<@" + str(user) + "> " + str(users[user]['monthly_invitation']) + "\n"

    to_print += "Daily print done"
    await channel.send(to_print)  # ch bot announcement? or delete


async def check_name_oda():
    await client.wait_until_ready()
    c = client.get_channel(ch_feedback)  # ch bot announcement? or delete

    guild = discord.utils.get(client.guilds, name=GUILD)

    list_oda_clan_in_name = ['oda clan', 'odaclan']

    for user_id in users.keys():
        member = discord.utils.get(guild.members, id=int(user_id))
        # for i in list_oda_clan_in_name:
        if member is not None:
            if any(s in member.name.lower() for s in list_oda_clan_in_name):
                continue
            else:
                users[user_id]['oda_in_name'] = False

    await c.send("Hourly check to Oda in name done")  # ch bot announcement? or delete


async def monthly_podium_prices():
    await client.wait_until_ready()
    channel = client.get_channel(ch_announcements)  # ch bot announcement? or ch announcements

    for index_role in range(len(role_oda_clan) - 1, -1, -1):
        role = role_oda_clan[index_role]
        check_role_discount = False
        for p in role_oda_clan_discount[index_role]:
            if p is not None:
                check_role_discount = True
        print_leaderboard = ""
        if check_role_discount:
            users_subset = find_users_subset(role)
            board = sort_users_points(users_subset)
            print_leaderboard += "Congratulations for the winners of this month competition! \n"
            print_leaderboard += '<@&' + str(role_oda_clan_id[index_role]) + "> leaderboard \n \n"
            keys = list(board.keys())  # add the name of the people in the leaderboard
            values = list(board.values())
            discount_values = role_oda_clan_discount[index_role]
            n_keys = len(keys)
            for i in range(np.min([len(discount_values), n_keys])):
                print_leaderboard += str(i + 1) + ". <@" + str(keys[i]) + "> " + str(values[i]["points"]) + " "
                if discount_values[i] is not None:
                    print_leaderboard += "| " + str(discount_values[i]) + "% discount"
                print_leaderboard += "\n \n"
            await channel.send(print_leaderboard)


async def monthly_upgrade_roles():
    await client.wait_until_ready()
    channel = client.get_channel(ch_announcements)  # ch bot announcement? or ch announcements
    guild = discord.utils.get(client.guilds, name=GUILD)

    for up_down in range(2):
        for index_role in range(len(role_oda_clan) - 1, -1, -1):
            role = role_oda_clan[index_role]
            print_up_down = ""
            perc = role_oda_clan_percentage[index_role][up_down]
            if perc is not None:
                users_subset = find_users_subset(role)
                board = sort_users_points(users_subset)
                keys = list(board.keys())  # add the name of the people in the leaderboard

                if up_down == 0:  # percentage up
                    print_up_down += "Congratulations! You are the best <@&" + str(role_oda_clan_id[index_role]) + \
                                     "> of this month and you are upgraded to " + role_oda_clan[index_role + 1] + "\n\n" # not role but role id
                    index_percentage_target = int(np.ceil(perc * len(keys) / 100))
                    for i in range(index_percentage_target):
                        user = guild.get_member(int(keys[i]))
                        print_up_down += "<@" + str(keys[i]) + "> "
                        await update_role(user, index_role + 1, notes="")
                    print_up_down += "\n\n"
                elif up_down == 1:
                    print_up_down += "That's unlucky! Your commitment was not enough for this month... " + \
                                     " so you are downgraded to " + role_oda_clan[index_role - 1] + "\n\n"
                    index_percentage_target = int(np.ceil(perc * len(keys) / 100))
                    for i in range(index_percentage_target, len(keys)):
                        user = guild.get_member(int(keys[i]))
                        print_up_down += "<@" + str(keys[i]) + "> "
                        await update_role(user, index_role - 1, notes="")

                await channel.send(print_up_down)


async def update_data(user, inviter_id=None, is_new_member=False, up_role_ds=True):
    id_user = str(user.id)
    if id_user not in users.keys():
        print('New user is: ' + id_user + " Invited id in update data: ", inviter_id)
        points_inviter = None
        if inviter_id is not None:
            if inviter_id in users.keys():
                invite_cap = 3.0
                diminishing_factor = 0.5
                points_inviter = int(np.max([1 - diminishing_factor * np.floor(users[inviter_id]['monthly_invitation']
                                                                               / invite_cap), diminishing_factor]) *
                                     points_invitation_per_role[role_oda_clan.index(users[inviter_id]['role'])])
                users[inviter_id]['monthly_invitation'] += 1
                update_point(inviter_id, points_inviter)
                update_data_backup(p=points_inviter, cat='i')
            else:
                inviter_id = None
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        users[id_user] = {}
        actual_role_index = 0
        for i in range(len(role_oda_clan_id)):
            tmp_role_id = role_oda_clan_id[i]
            tmp = discord.utils.get(user.roles, id=tmp_role_id)
            if tmp is not None:
                actual_role_index = i
        users[id_user]['role_id'] = role_oda_clan_id[actual_role_index]  # actual role of the user
        users[id_user]['role'] = role_oda_clan[actual_role_index]  # actual role of the user

        users[id_user]['points'] = 0  # actual number of points
        users[id_user]['daily'] = False  # if the user has claimed the daily prize
        users[id_user]['consecutive_daily'] = 0  # number of consecutive daily prizes
        users[id_user]['monthly_invitation'] = 0  # number of invitation in the current month
        users[id_user]['monthly_give_limit'] = 5000  # monthly give limit
        users[id_user]['multiplier'] = 1  # points multiplier
        users[id_user]['oda_in_name'] = True  # check if the person has oda clan in his name: start with True
                                              # -> if it becomes False the next day the multiplier is 1, otherwise 1.1
        users[id_user]['consecutive_oda'] = 0  # check if the person has oda clan in his name: start with True
        users[id_user]['invited_by'] = [inviter_id,
                                        points_inviter]  # [id of who invited him, points obtained with this invitation]
        users[id_user]['backup_roles'] = [[datetime2str(now, format='%Y/%m/%d'),
                                           role_oda_clan_lvl[actual_role_index]]]  # backup of roles updates: [date, up_role]
        users[id_user]['backup_invitation'] = []  # backup of invitations per month: [date, n_invitations]
        users[id_user]['backup_notes'] = []  # backup of notes: [date, notes]
        role = discord.utils.get(user.guild.roles, name=role_oda_clan[actual_role_index])
        if up_role_ds:
            await user.add_roles(role)
    elif is_new_member:
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        users[id_user]['role_id'] = role_oda_clan_id[0]  # actual role of the user
        users[id_user]['role'] = role_oda_clan[0]  # actual role of the user
        users[id_user]['points'] = 0  # actual number of points
        users[id_user]['daily'] = False  # if the user has claimed the daily prize
        users[id_user]['consecutive_daily'] = 0  # number of consecutive daily prizes
        users[id_user]['monthly_invitation'] = 0  # number of invitation in the current month
        users[id_user]['multiplier'] = 1  # points multiplier
        users[id_user]['oda_in_name'] = True  # check if the person has oda clan in his name: start with True
        users[id_user]['consecutive_oda'] = 0  # check if the person has oda clan in his name: start with True
        # -> if it becomes False the next day the multiplier is 1, otherwise 1.1
        users[id_user]['backup_roles'].append([datetime2str(now, format='%Y/%m/%d'),
                                           role_oda_clan_lvl[0]])  # backup of roles updates: [date, up_role]
        users[id_user]['backup_invitation'] = []  # backup of invitations per month: [date, n_invitations]
        users[id_user]['backup_notes'].append([datetime2str(now, format='%Y/%m/%d'),
                                           'Member was already in the clan before'])  # backup of notes: [date, notes]
        role = discord.utils.get(user.guild.roles, name=role_oda_clan[0])
        if up_role_ds:
            await user.add_roles(role)


async def cmd_acc(message):
    if message.content.startswith('oda.acc'):
        list_user_message = message.mentions
        message_reply = ""
        if list_user_message:  # check if this is a bot
            for i in range(len(list_user_message)):
                user = list_user_message[i]
                id_user = str(user.id)
                user_role_index = role_oda_clan.index(users[id_user]['role'])
                if user_role_index < dict_index_roles['daimyo']:
                    message_reply += (user.name + " is a " + users[id_user]['role'] + " with "
                                      + str(users[id_user]['points']) + " ODA points! He has invited " +
                                      str(users[id_user]['monthly_invitation']) + " people this month! \n")
                else:
                    message_reply += "You cannot ask for info on Daimyō and Ten'nō accounts"
        else:
            user = message.author
            id_user = str(user.id)
            message_reply += ("You are a " + users[id_user]['role'] + " with "
                              + str(users[id_user]['points']) + " ODA points! You have invited " +
                              str(users[id_user]['monthly_invitation']) + " people this month! ")
        await message.reply(message_reply, mention_author=True)


async def cmd_up_role(message):
    if message.content.startswith('oda.up_role'):
        user = message.author
        id_user = str(user.id)
        role_author_id = users[id_user]['role_id']
        index_role_author = role_oda_clan_id.index(role_author_id)
        if index_role_author < dict_index_roles['daimyo']:
            return
        list_user_to_up = message.mentions
        if list_user_to_up:  # check if this is a bot
            words = message.content.split()
            is_format_correct, string_output, info = check_format_input(words, format='%oc%roc')
            if not is_format_correct:
                await message.reply(string_output, mention_author=True)
            else:
                if info['role_command'] in role_oda_clan_command[:dict_index_roles['daimyo']]:
                    for user_to_up in list_user_to_up:
                        id_user_to_up = str(user_to_up.id)
                        if id_user_to_up in users.keys():
                            if int(users[id_user_to_up]['role_id']) in role_oda_clan_id[:dict_index_roles['daimyo']]:
                                index_role_user_to_up = role_oda_clan_command.index(info['role_command'])
                                await update_role(user_to_up, index_role_user_to_up)
                                await message.reply(user_to_up.name + " has been update to " + users[id_user_to_up]['role'],
                                                    mention_author=False)
                            else:
                                await message.reply("You cannot modify the role of a Daimyō or a Ten'nō  ",
                                                    mention_author=True)
                        else:
                            await message.reply(user_to_up.name + " not in the guild or not active.",
                                                mention_author=True)
                else:
                    await message.reply("This command is implemented only to upgrade members from hinin to samurai " +
                                        "but you have asked to upgrade to " +
                                        info['role_command'], mention_author=True)
        else:
            await message.reply("No mentions", mention_author=True)


async def cmd_leader_up_role(message):
    if message.content.startswith('oda.leader_up_role'):
        user = message.author
        id_user = str(user.id)
        role_author_id = users[id_user]['role_id']
        index_role_author = role_oda_clan_id.index(role_author_id)
        if index_role_author < dict_index_roles['tenno']:
            return
        list_user_to_up = message.mentions
        if list_user_to_up:  # check if this is a bot
            words = message.content.split()
            is_format_correct, string_output, info = check_format_input(words, format='%oc%roc')
            if not is_format_correct:
                await message.reply(string_output, mention_author=True)
            else:
                for user_to_up in list_user_to_up:
                    id_user_to_up = str(user_to_up.id)
                    if id_user_to_up in users.keys():
                        index_role_user_to_up = role_oda_clan_command.index(info['role_command'])
                        await update_role(user_to_up, index_role_user_to_up)
                        await message.reply(user_to_up.name + " has been update to " + users[id_user_to_up]['role'],
                                            mention_author=False)
                    else:
                        await message.reply(user_to_up.name + " not in the guild or not active.",
                                            mention_author=True)
        else:
            await message.reply("No mentions", mention_author=True)


async def cmd_give(message):
    if message.content.startswith('oda.give'):
        user = message.author
        id_user = str(user.id)
        list_user_to_up = message.mentions
        if list_user_to_up:  # check if this is a bot
            if len(list_user_to_up) == 1:
                user_to_up = list_user_to_up[0]
                id_user_to_up = str(user_to_up.id)
                words = message.content.split()
                if words[1].isdigit():
                    p = int(words[1])
                    if 1 <= p <= users[id_user]["points"]:
                        if p <= users[id_user_to_up]['monthly_give_limit']:
                            update_point(id_user_to_up, p)  # add user name
                            update_point(id_user, -p)  # add user name
                            update_data_backup(p=p, cat='g')
                            users[id_user_to_up]['monthly_give_limit'] -= p
                            await message.reply("You give " + words[1] + " ODA points to <@" + id_user_to_up
                                                + ">. ", mention_author=True)
                        else:
                            await message.reply("<@" + id_user_to_up + "> can still receive this month just "
                                                + str(users[id_user_to_up]['monthly_give_limit']) + " ODA points..")
                    else:
                        await message.reply("Wrong number of ODA points to add ", mention_author=True)
                elif words[1] == 'all':
                    p = users[id_user]["points"]
                    update_point(id_user_to_up, p)  # add user name
                    update_point(id_user, -p)  # add user name
                    update_data_backup(p=p, cat='g')
                    await message.reply("You give " + words[1] + " ODA points to <@" + id_user_to_up
                                        + ">. ", mention_author=True)
                else:
                    await message.reply("Wrong number of ODA points to add ", mention_author=True)
            else:
                await message.reply("Too many mentions, you can donate your ODA points at one person at a time ",
                                    mention_author=True)
        else:
            await message.reply("No mentions ", mention_author=True)


async def update_role(user, index_role, notes="", up_role_ds=True):
    id_user = str(user.id)
    # old_role = discord.utils.get(user.guild.roles, name=users[id_user]['role'])
    old_role = discord.utils.get(user.guild.roles, id=users[id_user]['role_id'])
    # old_role_2 = discord.utils.get(user.guild.roles, id=976580535444963418)
    # role = discord.utils.get(user.guild.roles, name=role_oda_clan[index_role])
    role = discord.utils.get(user.guild.roles, id=role_oda_clan_id[index_role])
    users[id_user]['role_id'] = role_oda_clan_id[index_role]
    users[id_user]['role'] = role_oda_clan[index_role]
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    users[id_user]['backup_roles'].append([datetime2str(now, '%Y/%m/%d'), role_oda_clan_lvl[index_role]])  # format
    if up_role_ds:
        await user.add_roles(role)
        await user.remove_roles(old_role)
    if notes != "" and notes != " ":
        users[id_user]['backup_notes'].append([datetime2str(now, '%Y/%m/%d'), notes])


async def cmd_up_point(message):
    if message.content.startswith('oda.up_point'):
        user = message.author
        id_user = str(user.id)
        role_author_id = users[id_user]['role_id']
        index_role_author = role_oda_clan_id.index(role_author_id)
        if index_role_author < dict_index_roles['daimyo']:
            return
        list_user_to_up = message.mentions
        if list_user_to_up:  # check if this is a bot
            words = message.content.split()
            is_format_correct, string_output, info = check_format_input(words, format='%oc%p')  # %t
            if is_format_correct:
                for user_to_up in list_user_to_up:
                    id_user_to_up = str(user_to_up.id)
                    update_point(id_user_to_up, info['points'])  # add user name
                    await message.reply("You add " + str(info['points']) + " ODA points to " + user_to_up.name +
                                        " and he has now " + str(users[id_user_to_up]['points']) + " ODA points",
                                        mention_author=True)
            else:
                await message.reply(string_output, mention_author=True)
        else:
            await message.reply("No mentions ", mention_author=True)


def update_point(id_user, p):
    users[id_user]['points'] += int(p)


def find_users_subset(role):
    users_subset = {key: value for key, value in users.items() if value["role"] in role}
    return users_subset


def sort_users_points(users_subset):
    users_sorted = dict(sorted(users_subset.items(), key=lambda x: x[1]["points"], reverse=True))
    return users_sorted


async def check_pos_user_board(board, id_user, role):
    to_add_to_print_leaderboard = ""
    keys = list(board.keys())
    values = list(board.values())
    index_role = role_oda_clan.index(role)
    user_index = keys.index(id_user)
    percentage = role_oda_clan_percentage[index_role]
    percentage_user = np.ceil((user_index + 1) / len(keys) * 100)
    perc = percentage[0]
    if perc is not None:
        if percentage_user > perc:
            index_percentage_target = int(np.ceil(perc * len(keys) / 100))
            to_add_to_print_leaderboard += "You are not in the top " + str(perc) + \
                                           "% of the" + role + " leaderboard, so you will not upgrade to " + \
                                           role_oda_clan[index_role + 1] + " next month. You need " + \
                                           str(np.abs(values[index_percentage_target]['points'] - \
                                                      values[user_index]['points'])) + \
                                           " ODA points to reach position " + str(index_percentage_target) + ". \n \n"
        else:
            to_add_to_print_leaderboard += "You are in the top " + str(perc) + \
                                           "% of the" + role + " leaderboard, so you will upgrade to " + \
                                           role_oda_clan[index_role + 1] + \
                                           " next month, if you maintain this position. \n \n"
    perc = percentage[1]
    if perc is not None:
        if percentage_user > perc:
            index_percentage_target = int(perc * len(keys) / 100)
            to_add_to_print_leaderboard += "You are in the last " + str(100 - perc) + \
                                           "% of the" + role + " leaderboard, so you will downgrade to " + \
                                           role_oda_clan[index_role - 1] + " next month. You need " + \
                                           str(np.abs(values[index_percentage_target]['points'] - \
                                                      values[user_index]['points'])) + \
                                           " ODA points to reach position " + str(index_percentage_target + 1) \
                                           + ". \n \n"

    if (index_role in [dict_index_roles['noka'], dict_index_roles['samurai']]) and (user_index <= 9):
        list_positions = ["first", "second", "third", 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth']
        to_add_to_print_leaderboard += "You are in the " + list_positions[user_index] + " position of the " + role + \
                                       " leaderboard, so you will earn a discount of " + \
                                       str(role_oda_clan_discount[index_role][user_index]) + \
                                       "% to become a Samurai, if you maintain this" + \
                                       " position until the end of the month.\n \n"
    return to_add_to_print_leaderboard


async def cmd_leaderboard(message):
    role_leaderboard = []
    if message.content.startswith('oda.board'):
        role_leaderboard = role_oda_clan[dict_index_roles['shonin']:dict_index_roles['daimyo']]
    if message.content.startswith('oda.shonin'):
        role_leaderboard = [role_oda_clan[dict_index_roles['shonin']]]
    if message.content.startswith('oda.shokunin'):
        role_leaderboard = [role_oda_clan[dict_index_roles['shokunin']]]
    if message.content.startswith('oda.noka'):
        role_leaderboard = [role_oda_clan[dict_index_roles['noka']]]
    if message.content.startswith('oda.samurai'):
        role_leaderboard = [role_oda_clan[dict_index_roles['samurai']]]
    if role_leaderboard:
        user = message.author
        id_user = str(user.id)
        print_leaderboard = ""

        users_subset = find_users_subset(role_leaderboard)
        board = sort_users_points(users_subset)
        n_to_print = np.min([10, len(board.keys())])
        if n_to_print == 0:
            all_roles = ", ".join(str(e) for e in role_leaderboard)
            print_leaderboard += "There are no " + all_roles + " in this server!"
        else:
            if message.content.startswith('oda.board'):
                print_leaderboard += "General leaderboard \n \n"
            else:
                print_leaderboard += role_leaderboard[0] + " leaderboard \n \n"
            keys = list(board.keys())  # add the name of the people in the leaderboard
            values = list(board.values())
            for i in range(n_to_print):
                print_leaderboard += str(i + 1) + ". <@" + str(keys[i]) + "> " + str(values[i]["points"]) \
                                     + " ODA points"
                if message.content.startswith('oda.board'):  # optional: we must decide if we want to let the colour of the user do the work
                    print_leaderboard += " | " + users[str(keys[i])]["role"]
                print_leaderboard += "\n\n"

            if id_user in keys:
                user_index = keys.index(id_user)
                print_leaderboard += "You are in the top " + str(np.ceil((user_index + 1) / len(board.keys()) * 100)) +\
                                     "%, at position " + str(user_index + 1) + ". \n\n"
                if len(role_leaderboard) == 1:
                    print_leaderboard += await check_pos_user_board(board, id_user, role_leaderboard[0])
            else:
                print_leaderboard += "You are not in this leaderboard."

        await message.reply(print_leaderboard, mention_author=False)


async def cmd_daily(message):
    if message.content.startswith('oda.daily'):
        user = message.author
        id_user = str(user.id)
        print_daily = ""
        if users[id_user]['daily']:
            print_daily += "You have already claimed your daily ODA points!"
        else:
            user_role_id = users[id_user]['role_id']
            points_to_add = int(np.ceil(points_daily_per_role[role_oda_clan_id.index(user_role_id)] *
                                    (1 + users[id_user]['consecutive_daily']/100)))
            update_point(id_user, points_to_add)
            update_data_backup(p=points_to_add, cat='d')
            users[id_user]['daily'] = True
            users[id_user]['consecutive_daily'] += 1
            print_daily += "Congratulations! You gain " + str(points_to_add) + " ODA points! "
            print_daily += "You are in a " + str(users[id_user]['consecutive_daily']) + " days streak!"

        await message.reply(print_daily, mention_author=False)


def update_data_backup(p, cat):
    # p = points, cat = category ('d'=daily, 'i'=invit, 'r'=react, 'g'=give, 'a'=abandon)
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    id_data = datetime2str(now, '%Y/%m/%d')
    if id_data not in data_backup.keys():
        data_backup[id_data] = {}

        data_backup[id_data]['n_daily'] = 0
        data_backup[id_data]['p_daily'] = 0

        data_backup[id_data]['n_invit'] = 0
        data_backup[id_data]['p_invit'] = 0

        data_backup[id_data]['n_react'] = 0
        data_backup[id_data]['p_react'] = 0

        data_backup[id_data]['n_survey'] = 0
        data_backup[id_data]['p_survey'] = 0

        data_backup[id_data]['n_give'] = 0
        data_backup[id_data]['p_give'] = 0

        data_backup[id_data]['n_abandon'] = 0
        data_backup[id_data]['p_abandon'] = 0
    if cat == 'd':
        data_backup[id_data]['n_daily'] += 1
        data_backup[id_data]['p_daily'] += p
    if cat == 'i':
        data_backup[id_data]['n_invit'] += 1
        data_backup[id_data]['p_invit'] += p
    if cat == 'r':
        if p < 0:
            data_backup[id_data]['n_react'] -= 1
            data_backup[id_data]['p_react'] += p
        else:
            data_backup[id_data]['n_react'] += 1
            data_backup[id_data]['p_react'] += p
    if cat == 's':
        if p < 0:
            data_backup[id_data]['n_survey'] -= 1
            data_backup[id_data]['p_survey'] += p
        else:
            data_backup[id_data]['n_survey'] += 1
            data_backup[id_data]['p_survey'] += p
    if cat == 'g':
        data_backup[id_data]['n_give'] += 1
        data_backup[id_data]['p_give'] += p
    if cat == 'a':
        data_backup[id_data]['n_abandon'] += 1
        data_backup[id_data]['p_abandon'] += p


async def reactions_up_points(payload):
    if payload.channel_id not in ch_list_reactions:
        return

    id_user = str(payload.user_id)
    if id_user not in users.keys():
        print('no point for reaction given to this id: ', id_user)
        return
    user_role_id = users[id_user]['role_id']
    points_to_add = points_reaction_per_role[role_oda_clan_id.index(user_role_id)]
    # points_reaction_max = points_reaction_per_role[role_oda_clan_id.index(user_role_id)]

    # channel = await client.fetch_channel(payload.channel_id)
    # message = await channel.fetch_message(payload.message_id)

    # message_time = message.created_at
    # timezone = pytz.timezone("UTC")
    # message_time = timezone.localize(message_time)
    # now = datetime.datetime.now(tz=datetime.timezone.utc)
    # time_gap = now - message_time
    # time_gap = time_gap.total_seconds()
    # points_to_add = int(np.max([np.ceil(points_reaction_max - (points_reaction_max / 10) *
    #                                     (time_gap / (60 * 60 * 24)) ** (3 / 2)), int(points_reaction_max / 5)]))
    # # if at time 0 -> 10 points: after 1 day 9 points, 2 days 7 points, 3 days 5 points,
    # # 4 days 2 points, > 5 days 1 points
    update_point(id_user, points_to_add)
    update_data_backup(p=points_to_add, cat='r')


async def reactions_down_points(payload):
    if payload.channel_id not in ch_list_reactions:
        return

    id_user = str(payload.user_id)
    if id_user not in users.keys():
        print('no point for reaction taken to this id: ', id_user)
        return
    user_role_id = users[id_user]['role_id']
    points_to_del = points_reaction_per_role[role_oda_clan_id.index(user_role_id)]
    # points_reaction_max = points_reaction_per_role[role_oda_clan_id.index(user_role_id)]

    # channel = await client.fetch_channel(payload.channel_id)
    # message = await channel.fetch_message(payload.message_id)

    # message_time = message.created_at
    # timezone = pytz.timezone("UTC")
    # message_time = timezone.localize(message_time)
    # now = datetime.datetime.now(tz=datetime.timezone.utc)
    # time_gap = now - message_time
    # time_gap = time_gap.total_seconds()
    # points_to_del = int(np.max([np.ceil(points_reaction_max - (points_reaction_max / 10) *
    #                                     (time_gap / (60 * 60 * 24)) ** (3 / 2)), int(points_reaction_max / 5)]))
    # # if at time 0 -> 10 points: after 1 day 9 points, 2 days 7 points, 3 days 5 points,
    # # 4 days 2 points, > 5 days 1 points
    update_point(id_user, -points_to_del)
    update_data_backup(p=-points_to_del, cat='r')


async def reactions_surveys_up_points(payload):
    if payload.channel_id not in ch_list_surveys:
        return

    id_user = str(payload.user_id)
    user_role_id = users[id_user]['role_id']
    points_survey = points_survey_per_role[role_oda_clan_id.index(user_role_id)]

    channel = await client.fetch_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    tot_reactions = 0
    for r in message.reactions:

        if payload.member in await r.users().flatten() and not payload.member.bot:
            tot_reactions += 1

    if tot_reactions == 1:
        update_point(id_user, points_survey)
        update_data_backup(p=points_survey, cat='s')


async def reactions_surveys_down_points(payload):
    if payload.channel_id not in ch_list_surveys:
        return

    id_user = str(payload.user_id)
    user_role_id = users[id_user]['role_id']
    points_surveys = points_survey_per_role[role_oda_clan_id.index(user_role_id)]

    channel = await client.fetch_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    tot_reactions = 0
    for r in message.reactions:
        if payload.member in await r.users().flatten() and not payload.member.bot:
            tot_reactions += 1

    if tot_reactions == 0:
        update_point(id_user, -points_surveys)
        update_data_backup(p=-points_surveys, cat='s')


def find_notes(words, delimiters):
    start_notes = -1
    end_notes = -1
    found_once = [False, False]
    for i in range(len(words)):
        for j in range(2):
            if words[i] == delimiters[j]:
                if not found_once[j]:
                    start_notes = i
                    found_once[j] = True
                else:
                    return "Error multiple delimiters"
    if start_notes >= end_notes:
        return "Error swap delimiters"
    return " ".join(w for w in words[start_notes + 1:end_notes])


def find_invite_by_code(invite_list, code):
    for inv in invite_list:
        if inv.code == code:
            return inv


def validate_date(d, format=['%Y/%m/%d', '%Y-%m-%d']):
    for f in format:
        try:
            datetime.datetime.strptime(d, f)
            return True
        except ValueError:
            continue
    return False


def force_format_datetime(d, old='-', new='/', max_sub=2):
    return d.replace(old, new, max_sub)


def check_format_input(words, format):
    # %oc = oda command,  %ro = role oda clan,  %roc = role oda clan command, %d = date, %dt = datetime,
    # %p = points, %c = currency, %a = amount, %m = n_months, %t = text
    format_poss = ['oc', 'ro', 'roc', 'd', 'dt', 'p', 'c', 'a', 'm', 't']
    format_split = re.split('%', format)
    is_format_correct = False
    string_output = ''
    info = {'oda_command': '', 'role': '', 'role_command': '', 'date': '', 'datetime': '', 'points': None,
            'amount': None, 'currency': '', 'n_months': None, 'text': ''}

    format_split = [el for el in format_split if el != '']
    if not format_split:
        string_output += 'Incorrect format: the format is empty'
        return is_format_correct, string_output, info
    for f in format_split:
        if f not in format_poss:
            string_output += 'Incorrect format: ' + f + ' not an available format'
            return is_format_correct, string_output, info

    if len(set(format_split)) != len(format_split):
        string_output += 'Incorrect format: some formats are repeated not an available format'
        return is_format_correct, string_output, info

    for i in range(len(format_split)):
        f = format_split[i]
        w = words[i]
        if f == 'oc':
            if w not in cmd_list:
                string_output += 'Incorrect oda command: ' + w + ' not a command'
                return is_format_correct, string_output, info
            info['oda_command'] = w
        if f == 'ro':
            if w not in role_oda_clan:
                string_output += 'Incorrect role: ' + w + ' not a role in Oda clan'
                return is_format_correct, string_output, info
            info['role'] = w
        if f == 'roc':
            if w not in role_oda_clan_command:
                string_output += 'Incorrect command role: ' + w + ' not a command role in Oda clan'
                return is_format_correct, string_output, info
            info['role_command'] = w
        if f == 'd':
            date_format = ['%Y/%m/%d', '%Y-%m-%d']
            if not validate_date(w, format=date_format) and w != 'now':
                string_output += 'Incorrect date format: ' + w + ' has not the following format ' + date_format
                return is_format_correct, string_output, info
            if w == 'now':
                now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
                info['date'] = datetime2str(now, "%Y/%m/%d")
            elif validate_date(w, format=['%Y-%m-%d']):
                info['date'] = force_format_datetime(w, old='-', new='/', max_sub=2)
            else:
                info['date'] = w
        if f == 'dt':
            date_format = ['%Y/%m/%d-%H:%M:%S', '%Y-%m-%d-%H:%M:%S']
            if not validate_date(w, format=date_format) and w != 'now':
                string_output += 'Incorrect date format: ' + w + ' has not the following format ' + date_format
                return is_format_correct, string_output, info
            if w == 'now':
                now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
                info['datetime'] = datetime2str(now, "%Y/%m/%d-%H:%M:%S")
            if validate_date(w, format=['%Y-%m-%d-%H:%M:%S']):
                info['datetime'] = force_format_datetime(w, old='-', new='/', max_sub=2)
            else:
                info['datetime'] = w
        if f == 'p':
            try:
                info['points'] = int(w)
            except ValueError:
                string_output += 'Incorrect number format: ' + w + ' is not a number '
                return is_format_correct, string_output, info
        if f == 'c':
            if w not in currency_list:
                string_output += 'Incorrect currency format: ' + w + ' is not an available currency '
                return is_format_correct, string_output, info
            info['currency'] = w
        if f == 'a':
            try:
                info['amount'] = float(w)
                if info['amount'] < 0:
                    string_output += 'Incorrect number format: ' + w + ' is a negative number '
                    return is_format_correct, string_output, info
            except ValueError:
                string_output += 'Incorrect number format: ' + w + ' is not a number '
                return is_format_correct, string_output, info
        if f == 'm':
            try:
                info['n_months'] = int(w)
                if info['n_months'] < 0:
                    string_output += 'Incorrect months format: ' + w + ' is a negative number '
                    return is_format_correct, string_output, info
            except ValueError:
                string_output += 'Incorrect number format: ' + w + ' is not a number '
                return is_format_correct, string_output, info
        if f == 't':
            if w[:len(texts_delimiters[0])] != texts_delimiters[0]:
                string_output += 'Incorrect text delimiters: ' + w + ' does not start with ( '
                return is_format_correct, string_output, info
            all_text = " ".join(el for el in words)
            text_split = re.split(texts_delimiters_re, all_text)
            if len(text_split) != 3:
                string_output += 'Incorrect text delimiters: wrong number of text delimiters '
                return is_format_correct, string_output, info
            info['text'] = text_split[1]

    is_format_correct = True
    return is_format_correct, string_output, info


client.run(TOKEN)
now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
logging.warning('Finished at ' + datetime2str(now))

