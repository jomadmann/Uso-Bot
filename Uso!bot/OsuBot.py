# -*- coding: utf-8 -*-
"""
Created on Sat May 20 22:39:26 2017

@author: Renondedju
"""
import discord
import asyncio
import sys
import traceback
import subprocess
import sqlite3
import os
import re
from datetime import datetime
from osuapi import OsuApi, ReqConnector
import requests
import constants

#Uso !#7507

client = discord.Client()
commandPrefix = constants.Settings.commandPrefix

api = OsuApi(constants.Api.osuApiKey, connector=ReqConnector())
LogFile = open(constants.Paths.logsFile, "a")

mainChannel = None
logsChannel = None
botOwner = None
databasePath = constants.Paths.beatmapDatabase

#Colors
Color_Off='\x1b[0m'
Red='\x1b[1;31;40m'
Yellow='\x1b[1;33;40m'

def return_user_rank(discordId):
	if not discordId == constants.Settings.ownerDiscordId:
		conn = sqlite3.connect(databasePath)
		cursor = conn.cursor()
		cursor.execute("SELECT rank FROM users WHERE discordId = ?", (str(discordId),))
		try:
			rank = cursor.fetchall()[0][0]
		except IndexError:
			rank = 'USER'
		conn.close()
		if rank == "":
			rank = "USER"
		return rank
	return 'MASTER'

def refresh_all_pp_stats():
	conn = sqlite3.connect(databasePath)
	cursor = conn.cursor()
	cursor.execute("SELECT DiscordId, OsuId FROM users")
	usersToRefresh = cursor.fetchall()
	for user in usersToRefresh:
		update_pp_stats(user[1], user[0])

def update_pp_stats(osuId, discordId):
	try:
		pp_average = get_pp_stats(osuId)
		if pp_average == False:
			return 1
		conn = sqlite3.connect(databasePath)
		cursor = conn.cursor()
		cursor.execute("UPDATE users SET ppAverage = ? WHERE DiscordId = ?", (str(pp_average), str(discordId),))
		conn.commit()
		print ("Pp stats updated for osuId : " + str(osuId) + " with discordId : " + str(discordId) + " - PP average = " + str(pp_average))
		return 0
	except:
		return 2

def get_pp_stats(osuId):
	global api
	try:
		results = api.get_user_best(osuId, limit = 20)
		pp_average = 0
		for beatmap in results:
			for item in beatmap:
				if item[0] == 'pp':
					pp_average += item[1]
		pp_average = pp_average/20
		return pp_average
	except:
		return False

def link_user(discordId, osuName, osuId, rank):
	result = ""
	print ("Linking : discordId : " + str(discordId) + ", osuName : " + osuName + ", osuId : " + str(osuId) + " to Database.", end = " ")
	conn = sqlite3.connect(databasePath)
	cursor = conn.cursor()
	cursor.execute("SELECT * FROM users WHERE discordId = ?", (str(discordId),))
	if len(cursor.fetchall()) == 0:
		cursor.execute("""
		INSERT INTO users (discordId, osuName, osuId, rank) 
		VALUES (?, ?, ?, ?)
		""", (discordId, osuName, osuId, rank))
		conn.commit()
		print ("Added")
		result = "linked"
	else:
		cursor.execute("UPDATE users SET osuName = ?, osuId = ?, rank = ? WHERE discordId = ?", (osuName, str(osuId), rank, str(discordId)))
		conn.commit()
		print("Updated")
		result = "updated"
	conn.close()
	return result

def add_beatmap_to_queue(url):
	if not(url in new_beatmap_list):
		new_beatmaps_file = open("/home/pi/DiscordBots/OsuBot/beatmapsFiles/newBeatmaps.txt", "a")
		new_beatmaps_file.write('\n' + url)
		new_beatmaps_file.close()
		print ("Added " + url + " to beatmap queue")

def return_simple_beatmap_info(url, oppaiParameters):
	url = url.replace('/b/', '/osu/').split("&", 1)[0]
	if oppaiParameters == "":
		command = "curl " + url + " | /home/pi/DiscordBots/Oppai/oppai/oppai -"
	else:
		command = "curl " + url + " | /home/pi/DiscordBots/Oppai/oppai/oppai - " + oppaiParameters

	return get_infos(subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.read())

def return_beatmap_infos(url, oppaiParameters):
	#https://osu.ppy.sh/osu/37658
	url = url.replace('/b/', '/osu/').split("&", 1)[0]
	if oppaiParameters == "":
		command = "curl " + url + " | /home/pi/DiscordBots/Oppai/oppai/oppai -"
	else:
		command = "curl " + url + " | /home/pi/DiscordBots/Oppai/oppai/oppai - " + oppaiParameters

	#print (command)
	p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
	raw_data = p.stdout.read()
	pp_100, name, combo, stars, diff_params = get_infos(raw_data)
	if pp_100 == -1:
		pp_100 = pp_95 = name = combo = stars = diff_params = -1
		return pp_100, pp_95, name, combo, stars, diff_params
	else:
		p = subprocess.Popen(command + " 95%", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
		raw_data = p.stdout.read()
		pp_95, _, _, _, _ = get_infos(raw_data)
		return pp_100, pp_95, name, combo, stars, diff_params

def get_infos(row_datas):
	try:
		split_data = row_datas.split(b'\n')
		pp = split_data[35].replace(b'pp', b'').decode("utf-8")
		name = split_data[14].replace(b' - ', b'').decode("utf-8")
		combo = split_data[16].split(b'/')[0].decode("utf-8")
		stars = split_data[22].replace(b' stars', b'').decode("utf-8")
		diff_params = split_data[15].decode("utf-8")
		return pp, name, combo, stars, diff_params
	except:
		pp = name = combo = stars = diff_params = -1
		return pp, name, combo, stars, diff_params

def create_backup():
	os.system("cp " + constants.Paths.beatmapDatabase + " " + constants.Paths.backupDirrectory + "DatabaseBackup_"+datetime.now().strftime('%Y-%m-%d_%H:%M:%S')+".db")
	files = os.listdir(constants.Paths.backupDirrectory)
	files.sort()
	if (len(files)>10):
		os.system("rm " + constants.Paths.backupDirrectory + files[0])

async def send_big_message(channel, message):
	message = message.split("\n")
	finalMessage = ""
	for line in message:
		if len(line) + len(finalMessage) < 2000:
			finalMessage += line + '\n'
		else:
			await client.send_message(channel, finalMessage)
			finalMessage = ""
	if finalMessage != "":
		await client.send_message(channel, finalMessage)

async def User_embed(channel, username = "Test", pp="1000", rank_SS = "54258", rank_S = "5421", rank_A = "5412", worldRank = "1", localRank = "1", country = "fr", playcount = "10000", level = "100", osuId = "7418575", totalScore = "15105810824020", ranckedScore="8648428841842", accuracy="99.03%", hit_300="532454", hit_100="5324", hit_50="504"):

	embed = discord.Embed(title=username + " stats (" + country.upper() + ")")
	embed.set_thumbnail(url="https://a.ppy.sh/" + osuId)
	embed.add_field(name="General", value="__Performance:__ **" + pp + "pp\n:map:#" + worldRank + " :flag_"+ country.lower() +":#"+ localRank + "**\n__Playcount :__ **" + playcount + "**\n__Level :__ **" + level + "**\n__Accuracy :__ **" + accuracy + "**", inline=True)
	embed.add_field(name="ᅠ", value="[Profile](https://osu.ppy.sh/users/" + osuId + ") / [Osu!Track](https://ameobea.me/osutrack/user/" + username + ") / [PP+](https://syrin.me/pp+/u/"+username+") / [Osu!Chan](https://syrin.me/osuchan/u/" + username + ")\n__Total score :__ **"+totalScore+"**\n__Rancked score :__ **" + ranckedScore + "**", inline=True)
	embed.add_field(name="Hits (300/100/50)", value="**" + hit_300 + "//" + hit_100 + "//" + hit_50 + "**", inline=True)
	embed.add_field(name="Ranks (SS/S/A)", value="**" + rank_SS + "//" + rank_S + "//" + rank_A + "**", inline=True)

	await client.send_message(channel, embed=embed)

async def Log(message, logLevel=0, content="", rank="USER"):

	if logLevel == 1:
		LogPrefix = "**WARNING : **"
		LogColor=discord.Colour.gold()
		print (Yellow + LogPrefix + message.author.name + " : " + message.content + Color_Off)
	elif logLevel == 2:
		LogPrefix = "__**ERROR : **__"
		LogColor=discord.Colour.red()
		print (Red + LogPrefix + message.author.name + " : " + message.content + Color_Off)
	else:
		LogPrefix = ""
		LogColor=discord.Colour.default()
		print (LogPrefix + message.author.name + " : " + message.content)

	date = datetime.now().strftime('%Y/%m/%d at %H:%M:%S')

	if content == "":
		fileOutput = str(logLevel) + str(date) + " -" + str(message.author.name) + " : " + str(message.content)
		LogFile.write(fileOutput + "\n")

		logEmbed = discord.Embed(description = LogPrefix + str(message.channel) + " : " + message.content, colour=LogColor)
		logEmbed.set_footer(text=date)
		if message.author.avatar == None:
			logEmbed.set_author(name = str(message.author.name) + " - " + str(rank))
		else:
			logEmbed.set_author(name = str(message.author.name) + " - " + str(rank), icon_url ="https://cdn.discordapp.com/avatars/"+str(message.author.id)+"/"+message.author.avatar+".png")

		if logLevel == 2:
			await client.send_message(botOwner, embed=logEmbed)

		await client.send_message(logsChannel, embed=logEmbed)
	else:

		fileOutput = str(logLevel) + str(date) + " -" + str(message.author.name) + " : " + str(message.content)
		LogFile.write(fileOutput + "\n")

		logEmbed = discord.Embed(description=content, colour=LogColor)
		logEmbed.set_footer(text=date)
		logEmbed.set_author(name = str(message.author.name), icon_url ="https://cdn.discordapp.com/avatars/"+str(message.author.id)+"/"+message.author.avatar+".png")

		if logLevel == 2:
			await client.send_message(botOwner, embed=logEmbed)

		await client.send_message(logsChannel, embed=logEmbed)

@client.event
async def on_ready():
	global mainChannel, logsChannel, visible, databasePath, botOwner
	mainChannel = client.get_server(constants.Settings.mainServerID).get_channel(constants.Settings.mainChannelId)
	logsChannel = client.get_server(constants.Settings.mainServerID).get_channel(constants.Settings.logsChannelId)
	print('Logged in !')

	for channel in client.private_channels:
		if str(channel.user) == "Renondedju#0204":
			botOwner = channel.user
			break

	await asyncio.sleep(0.1)
	hello = False
	if datetime.now().strftime('%H') == "00" or (set(sys.argv) & set(["refresh"])):
		message = await client.send_message(mainChannel, "<:empty:317951266355544065> Updating stats ...")
		try:
			print('Refreshing users stats ...')
			refresh_all_pp_stats()
			print(" - Done")
			print('Creating new backup ...', end="")
			create_backup()
			print(" Done !")
			await client.edit_message(message, "<:check:317951246084341761> Updating stats ... Done !")
		except:
			await client.edit_message(message, "<:xmark:317951256889131008> Updating stats ... Fail !")
		if not set(sys.argv) & set(["dev"]):
			await client.send_message(mainChannel, "<:online:317951041838514179> Uso!<:Bot:317951180737347587> is now online !")
			await client.change_presence(status=discord.Status('online'), game=discord.Game(name='Osu !'))
			hello = True
	print ('Ready !')
	if (set(sys.argv) & set(["online"])) and hello == False:
		await client.send_message(mainChannel, "<:online:317951041838514179> Uso!<:Bot:317951180737347587> is now online !")
		await client.change_presence(status=discord.Status('online'), game=discord.Game(name='o!help'))
	if set(sys.argv) & set(["dev"]):
		await client.change_presence(status=discord.Status('idle'), game=discord.Game(name='Dev mode'))
 
@client.event
async def on_message(message):
	global api, visible, LogFile

	rank = 'USER'
	if message.content.startswith(commandPrefix):
		rank = return_user_rank(message.author.id)
		await Log(message, 0, rank=rank)

	channel = message.channel
	if message.content.startswith(commandPrefix) and message.channel.is_private == False and message.content.startswith(commandPrefix + 'mute') == False:
		conn = sqlite3.connect(databasePath)
		cursor = conn.cursor()
		cursor.execute("SELECT state FROM muted WHERE serverID = ?", (str(message.server.id),))
		if cursor.fetchall()[0][0] == 'on':
			channel = message.author
		else:
			channel = message.channel

	if message.content.startswith(commandPrefix + 'test') and (rank in ['MASTER']):
		await client.send_message(message.channel, "Hi ! " + str(message.author) + " my command prefix is '" + commandPrefix + "'")
		await User_embed(channel)
		#Hey !

	if message.content.startswith(commandPrefix + 'backup') and (rank in ['MASTER']):
		create_backup()
		await client.send_message(channel, "Backup done")

	if message.content.startswith(commandPrefix + 'log') and (rank in ['MASTER']):
		await Log(message, 0)
		await Log(message, 1)
		await Log(message, 2)

	if message.content.startswith(commandPrefix + 'status') and (rank in ['ADMIN', 'MASTER']):
		parameters = message.content.replace(commandPrefix + 'status ', "")
		playmessage = parameters.split(" | ")[0]
		status = parameters.split(" | ")[1]
		await asyncio.sleep(1)
		await client.change_presence(game=discord.Game(name=playmessage), status=discord.Status(status))
		await client.send_message(channel, "Play message set to:``" + playmessage + "``, status set to:``" + status + "``")

	if message.content.startswith(commandPrefix + 'support') and (rank in ['USER', 'ADMIN', 'MASTER']):
		supportfile = open(constants.Paths.supportFile, "r")
		supportString = supportfile.read()
		supportfile.close()
		await client.send_message(channel, supportString)

	if (message.content.startswith(commandPrefix + 'recomandation') or message.content.startswith(commandPrefix + 'r')) and (rank in ['USER', 'ADMIN', 'MASTER']):
		conn = sqlite3.connect(databasePath)
		cursor = conn.cursor()
		cursor.execute("SELECT ppAverage FROM users WHERE DiscordId = ?", (str(message.author.id),))
		try:
			result = cursor.fetchall()[0][0]
		except:
			result = None
		if not(result == None):
			pp_average = int(result*0.97)
			if (pp_average == 0):
				await client.send_message(channel, "Please run the *" + commandPrefix + "update_pp_stats* command to set your stats for the first time in our database")
			else:
				pp_average_fluctuation = pp_average*0.05

				cursor.execute("Select recomendedBeatmaps From users where DiscordId = ?", (str(message.author.id),))
				alreadyRecomendedId = cursor.fetchall()[0][0]

				if alreadyRecomendedId == None:
					alreadyRecomendedId = "00000"

				cursor.execute("Select * from beatmaps where pp_95 >= ? and pp_95 <= ? and id not in (" + alreadyRecomendedId + ") Limit 1", (str(pp_average-pp_average_fluctuation), str(pp_average+pp_average_fluctuation)))

				recomendedBeatmap = cursor.fetchall()[0]
				url = recomendedBeatmap[0]
				name = recomendedBeatmap[1]
				diff_params = recomendedBeatmap[2]
				pp_100 = recomendedBeatmap[3]
				pp_95 = recomendedBeatmap[4]
				stars = recomendedBeatmap[5]
				combo = recomendedBeatmap[6]
				recomendedId = recomendedBeatmap[7]

				alreadyRecomendedId += "," + str(recomendedId)

				cursor.execute("UPDATE users SET recomendedBeatmaps = ? where DiscordId = ?", (alreadyRecomendedId, str(message.author.id)))
				conn.commit()
				conn.close()

				pp_98, _, _, _, _ = return_simple_beatmap_info(url, " 98%")

				description = "__100% pp__ : " + str(pp_100) + "\n" + "__98% pp__ : " + str(pp_98) + "\n" + "__95% pp__ : " + str(pp_95) + "\n" + "__Max Combo__ : " + str(combo) + "\n" + "__Stars__ : " + str(stars) + "\n" + str("*" + diff_params.upper() + "*")
				em = discord.Embed(title=str(name), description=description, colour=0xf44242, url=url)
				await client.send_message(channel, embed=em)
				print (recomendedBeatmap)
		else:
			await client.send_message(channel, "Uhh sorry, seems like you haven't linked your osu! account...\nPlease use the command *" + commandPrefix + "link_user 'Your osu username' or 'your osu Id'* to link the bot to your osu account !\nEx. " + commandPrefix + "link_user Renondedju")

	if message.content.startswith(commandPrefix + 'add_beatmap') and (rank in ['ADMIN', 'MASTER']):
		if (message.content.replace(commandPrefix + "add_beatmap ", "") == "" or not(message.content.replace(commandPrefix + "add_beatmap ", "")[0:19] == "https://osu.ppy.sh/")):
			await client.send_message(channel, "Invalid url !")
		else:
			pp_100, pp_95, name, combo, stars, diff_params = return_beatmap_infos(message.content.replace(commandPrefix + "add_beatmap ", ""))
			conn = sqlite3.connect(databasePath)
			cursor = conn.cursor()
			try:
				cursor.execute("""INSERT INTO "beatmaps" (url, name, diff_params, pp_100, pp_95, stars, combo, id) VALUES(?, ?, ?, ?, ?, ?, ?, ?)""", (message.content.replace(commandPrefix + "add_beatmap ", ""), name, diff_params, pp_100, pp_95, stars, combo, message.content.replace(commandPrefix + "add_beatmap ", "").replace("https://osu.ppy.sh/b/", "").replace("&m=0", "")))
				conn.commit()
				conn.close()
				await client.send_message(message.channel, "Addition done !")
			except sqlite3.IntegrityError:
				await client.send_message(message.channel, "This map is already in the Database !")
	
	if message.content.startswith(commandPrefix + 'add_beats') and (rank in ['MASTER']):

		if str(message.author.id) == constants.Settings.ownerDiscordId:

			await client.send_message(logsChannel, Log(str(message.author), message.content, 0))

			beatmapfile = open(message.content.replace(commandPrefix + 'add_beats ', ""), "r")
			beatmapToProcess = beatmapfile.read().split('\n')
			await client.send_message(message.channel, "<:streaming:317951088646946826> Starting the import of " + str(len(beatmapToProcess)) + " beatmaps")
			await asyncio.sleep(0.1)
			await client.change_presence(status=discord.Status('dnd'), game=discord.Game(name='Processing ...'))

			conn = sqlite3.connect(databasePath)

			await client.send_message(logsChannel, Log(str(message.author), "Ready to add " + str(len(beatmapToProcess)) + " beatmaps to the Database", 1))

			cursor = conn.cursor()
			processed = 1
			done = 0
			infoError = 0
			alreadyExists = 0
			for beatmapUrl in beatmapToProcess:

				print ("Processing " + beatmapUrl + " - " + str(processed) + "/" + str(len(beatmapToProcess)), end="")
				cursor.execute("select url from beatmaps where url = ?", (beatmapUrl,))
				if len(cursor.fetchall()) == 0:
					pp_100, pp_95, name, combo, stars, diff_params = return_beatmap_infos(beatmapUrl, "")
					if not (pp_100 == -1):
						try:
							cursor.execute("""INSERT INTO "beatmaps" (url, name, diff_params, pp_100, pp_95, stars, combo, id) VALUES(?, ?, ?, ?, ?, ?, ?, ?)""", (beatmapUrl, name, diff_params, pp_100, pp_95, stars, combo, beatmapUrl.replace("https://osu.ppy.sh/b/", "").replace("&m=0", "")))
							conn.commit()
							print (" - Done")
							await client.send_message(logsChannel, "<:check:317951246084341761> " + beatmapUrl + " ( "+str(processed) + "/" + str(len(beatmapToProcess))  +" ) - Done")
							done += 1
						except sqlite3.IntegrityError:
							print (" - Can't get beatmap infos !")
							await client.send_message(logsChannel, "<:xmark:317951256889131008> " + beatmapUrl + " ( "+str(processed) + "/" + str(len(beatmapToProcess))  +" ) - Can't get beatmap infos !")
							infoError += 1
					else:
						print (" - Can't get beatmap infos !")
						await client.send_message(logsChannel, "<:xmark:317951256889131008> " + beatmapUrl + " ( "+str(processed) + "/" + str(len(beatmapToProcess))  +" ) - Can't get beatmap infos !")
						infoError += 1
				else:
					print (" - Already exists")
					await client.send_message(logsChannel, "<:xmark:317951256889131008> " + beatmapUrl + " ( "+str(processed) + "/" + str(len(beatmapToProcess))  +" ) - Already exists")
					alreadyExists += 1
				processed += 1
			conn.close()

			await client.send_message(logsChannel, Log(str(message.author),  "Successfuly added " + str(len(beatmapToProcess)) + " beatmaps to the database", 1))
			await client.send_message(message.channel, "<:online:317951041838514179> Back online ! - __Done :__ " + str(done) + " , __InfoError :__ " + str(infoError) + " , __Already exists :__ " + str(alreadyExists))
			await asyncio.sleep(0.1)
			await client.change_presence(status=discord.Status('online'), game=discord.Game(name='Osu !'))

		else:
			await client.send_message(logsChannel, Log(str(message.author), "tried to add multiple beatmaps", 1))
			await client.send_message(message.channel, "Sorry, Only Renondedju can do this !")

	if message.content.startswith(commandPrefix + 'mute') and (rank in ['USER', 'ADMIN', 'MASTER']) and (message.channel.permissions_for(message.author).administrator == True or str(message.author) == "Renondedju#0204"):
		if not (message.server.id == None):
			conn = sqlite3.connect(databasePath)
			cursor = conn.cursor()
			try :
				parameter = message.content.split(' ')[1]
			except:
				parameter = ''
			if parameter.lower() in ['on', 'off']:
				parameter = parameter.lower()
				cursor.execute("SELECT * FROM muted WHERE serverID = ?", (str(message.server.id),))
				if len(cursor.fetchall()) == 0:
					cursor.execute("INSERT INTO muted (serverID, state) VALUES (?, ?)", (message.server.id, parameter))
				else:
					cursor.execute("UPDATE muted SET state = ? WHERE serverID = ?", (parameter, str(message.server.id)))
				await client.send_message(message.channel, "Done !")
				conn.commit()
			else:
				await client.send_message(message.channel, "Wrong argument (expected 'on' or 'off')")
			conn.close()
		else:
			await client.send_message(message.channel, "You can't execute this command here (servers only)")

	if message.content.startswith(commandPrefix + 'pp') and (rank in ['USER', 'ADMIN', 'MASTER']):
		parameters = message.content.replace(commandPrefix + "pp ", "")
		url = parameters.split(" ")[0]
		try:
			oppaiParameters = parameters.split(" ")[1:len(parameters.split(" "))]
			oppaiParameters = " ".join(str(x) for x in oppaiParameters)
		except IndexError:
			oppaiParameters = ""

		if (parameters == "" or not(url[0:19] == "https://osu.ppy.sh/")):
			await client.send_message(channel, "Invalid url !")
		else:
			pp_100, pp_95, name, combo, stars, diff_params = return_beatmap_infos(url, oppaiParameters)
			
			if not(pp_100 == -1):

				#add_beatmap_to_queue(url)
				await client.send_message(client.get_server("310348632094146570").get_channel("315166181256593418"), Log(str(client.user.name), "Added " + url + " to beatmap queue", 0))
				description = "__100% pp__ : " + str(pp_100) + "\n" + "__95% pp__ : " + str(pp_95) + "\n" + "__combo max__ : " + str(combo) + "\n" + "__stars__ : " + str(stars) + "\n" + str("*" + diff_params + "*")
				em = discord.Embed(title=str(name), description=description, colour=0xf44242)
				await client.send_message(channel, embed=em)
			else:
				await client.send_message(channel, "Can't get beatmap info...")

	if message.content.startswith(commandPrefix + 'kill') and (rank in ['MASTER']):
		if str(message.author.id) == constants.Settings.ownerDiscordId:
			await client.send_message(logsChannel, Log(str(client.user.name), "Killing the bot !", 0))
			await client.send_message(message.channel, "Alright, killing myself ... bye everyone !")
			client.logout()
			client.close()
			LogFile.close()
			sys.exit("Bot has been shutdown by command correctly !")
		else:
			await client.send_message(logsChannel, Log(str(message.author), "tried to kill the bot !", 1))
			await client.send_message(message.channel, "Sorry, Only Renondedju can do this !")

	if message.content.startswith(commandPrefix + 'user') and (rank in ['USER', 'ADMIN', 'MASTER']):
		parameters = message.content.split(' ')
		results = api.get_user(parameters[1])
		if results == []:
			try:
				results = api.get_user(int(parameters[1]))
			except ValueError:
				await client.send_message(channel, "User not found!")
		stats = []
		if not (results == []):
			for item in results[0]:
				stats.append(item)
			await User_embed(channel, username=str(stats[17][1]), rank_SS=str(stats[6][1]), rank_S=str(stats[5][1]), rank_A=str(stats[4][1]) , pp=str(stats[13][1]), worldRank=str(stats[12][1]), localRank=str(stats[11][1]), country=stats[7][1], playcount=str(stats[10][1]), level=str(stats[9][1]), osuId = str(stats[16][1]), totalScore = str(stats[15][1]), ranckedScore = str(stats[14][1]), accuracy = str(stats[0][1])[0:4]+"%", hit_300 = str(stats[2][1]), hit_100 = str(stats[1][1]), hit_50 = str(stats[3][1]))
		else:
			await client.send_message(channel, "User not found!")

	if message.content.startswith(commandPrefix + 'link_user') and (rank in ['USER', 'ADMIN', 'MASTER']):
		parameters = message.content.replace(commandPrefix + 'link_user ', '')
		try:
			results = api.get_user(parameters)
			if results == []:
				results = api.get_user(int(parameters))
				print(results)
		except IndexError:
			await client.send_message(channel, "Something went wrong ...")

		stats = []
		if not (results == []):
			for item in results[0]:
				stats.append(item)
			osuId = stats[16][1]
			osuUsername = stats[17][1]
			userDiscordId = int(message.author.id)
			operationDone = link_user(userDiscordId, osuUsername, osuId, "USER")

			await client.send_message(channel, "Your account has been successfuly " + operationDone + " to ")
			#await Log(message, logLevel=0, content="Account linked")
			await User_embed(channel, username=str(stats[17][1]), pp=str(stats[13][1]), worldRank=str(stats[12][1]), localRank=str(stats[11][1]), country=stats[7][1], playcount=str(stats[10][1]), level=str(stats[9][1]), osuId = str(stats[16][1]), totalScore = str(stats[15][1]), ranckedScore = str(stats[14][1]), accuracy = str(stats[0][1])[0:4]+"%" )
			if operationDone == "linked":
				await client.send_message(channel, "Please wait while I'm updating your stats ...")

				if update_pp_stats(osuId, message.author.id) == 0:
					#await client.send_message(logsChannel, Log(str(client.user.name), "Successfuly updated " + str(message.author) + "'s pp stats", 0))
					await client.send_message(channel, "Successfuly updated " + str(message.author) + "'s pp stats")

				else:
					#await client.send_message(logsChannel, Log(str(client.user.name), "Unexpected error for " + str(message.author), 2))
					await client.send_message(channel, "Unexpected error, please try again later or contact Renondedju for more help")
		else:
			#await client.send_message(logsChannel, Log(str(client.user.name), "User not found", 0))
			await client.send_message(channel, "User not found!")

	if message.content.startswith(commandPrefix + 'update_pp_stats') and (rank in ['USER', 'ADMIN', 'MASTER']):
		conn = sqlite3.connect(databasePath)
		cursor = conn.cursor()
		cursor.execute("SELECT OsuId FROM users WHERE DiscordId = ?", (str(message.author.id),))
		osuId = cursor.fetchall()[0][0]
		conn.close()
		if not (osuId == None):
			result = update_pp_stats(osuId, message.author.id)
			if result == 0:
				await client.send_message(logsChannel, Log(str(client.user.name), "Succesfuly updated " + str(message.author) + "'s pp stats", 0))
				await client.send_message(channel, "Succesfuly updated " + str(message.author) + "'s pp stats")
			elif result == 1:
				await client.send_message(logsChannel, Log(str(client.user.name), "Wrong osu! id for " + str(message.author), 1))
				await client.send_message(channel, "Wrong osu! id for " + str(message.author) + ". Try to link your account with an osu! account by typing the command *" + commandPrefix + "link_user 'Your osu username'*")
			elif result == 2:
				await client.send_message(logsChannel, Log(str(client.user.name), "Unexpected error for " + str(message.author), 2))
				await client.send_message(channel, "Unexpected error, please try again later or contact Renondedju for more help")
		else:
			await client.send_message(logsChannel, Log(str(client.user.name), "Wrong osu! id for " + str(message.author), 1))
			await client.send_message(channel, "Wrong osu! id for " + str(message.author) + ". Try to link your account with an osu account by typing the command *" + commandPrefix + "link_user 'Your osu username'*")

	if message.content.startswith(commandPrefix + 'help') and (rank in ['USER', 'ADMIN', 'MASTER']):
		if rank == 'ADMIN':
			helpfile = open(constants.Paths.helpAdminFile, "r")
			helpString = helpfile.read()
			helpfile.close()
			await send_big_message(channel, helpString)
		elif rank == 'MASTER':
			helpfile = open(constants.Paths.helpMasterFile, "r")
			helpString = helpfile.read()
			helpfile.close()
			await send_big_message(channel, helpString)
		else:
			helpfile = open(constants.Paths.helpUserFile, "r")
			helpString = helpfile.read()
			helpfile.close()
			await send_big_message(channel, helpString)

@client.event
async def on_error(event, *args, **kwargs):
	message = args[0]

	channel = message.channel
	if message.content.startswith(commandPrefix) and message.channel.is_private == False and message.content.startswith(commandPrefix + 'mute') == False:
		conn = sqlite3.connect(databasePath)
		cursor = conn.cursor()
		cursor.execute("SELECT state FROM muted WHERE serverID = ?", (str(message.server.id),))
		if cursor.fetchall()[0][0] == 'on':
			channel = message.author
		else:
			channel = message.channel

	print (Red + traceback.format_exc() + Color_Off)
	await Log(message, content = "Message:\n" + message.content + "\n\n```" + traceback.format_exc() + "```", logLevel=2)
	await client.send_message(channel, "Oops ! Unexpected error :/\nGo to my personal server to ask for some help if needed !\nhttps://discordapp.com/invite/mEeMPyK")

client.run(constants.Api.discordToken)