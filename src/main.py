import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, Response, status
from fastapi.staticfiles import StaticFiles
import os
import wget
import multiprocessing
import threading
import requests

from models import *
from dawe import DaweDraft
from utils import construct_config
CACHE_DIRECTORY = "./cache"
PORT = "4557"
app = FastAPI()
active_games : dict[str, (threading.Thread, threading.Event)] = {}
ws_manager = {}
lock = threading.Lock()

@app.on_event("shutdown")
def shutdown_event():
    for game in active_games.values():
        print(game)
        if game[0].is_alive():
            game[1].set()
            game[0].join()


app.mount("/cache", StaticFiles(directory=CACHE_DIRECTORY), name="cache")

@app.websocket("/ws/{nameKey}")
async def websocket_end(websocket:WebSocket, nameKey: str):
    if nameKey not in ws_manager:
        ws_manager[nameKey] = ConnectionManager()

    await ws_manager[nameKey].connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager[nameKey].disconnect(websocket)

@app.put("/{nameKey}", status_code=201)
async def create_dawe_game(nameKey: str, match_data: Match, background_tasks: BackgroundTasks, response: Response):
    if not os.path.isdir(f"{CACHE_DIRECTORY}/{match_data.game_version}"):
        response.status_code = status.HTTP_424_FAILED_DEPENDENCY
        return "Game Version DATA not available"
    if nameKey in active_games and active_games[nameKey][0].is_alive():
        print(active_games[nameKey])
        active_games[nameKey][1].set()
        active_games[nameKey][0].join()

    event = multiprocessing.Event()
    
    thread = threading.Thread(target = dawe_game, args= (nameKey, match_data, PORT, ))
    active_games[nameKey] = (thread, event)
    thread.start()
    return f"DAWE session connected. Please, find it on /view/{nameKey}"

@app.put("/download/{game_version}", status_code=200)
async def download_game_data(game_version: str, response: Response):
    if os.path.isdir(f"{CACHE_DIRECTORY}/{game_version}"):
        response.status_code = status.HTTP_424_FAILED_DEPENDENCY
        return "Game Version DATA already available"
    thread = threading.Thread(target = download_data, args= (game_version, ))
    thread.start()

    pass

def download_data(game_version):
    os.mkdir(f"{CACHE_DIRECTORY}/{game_version}")
    os.mkdir(f"{CACHE_DIRECTORY}/{game_version}/champion")

    champ_data = requests.get(f"http://ddragon.leagueoflegends.com/cdn/{game_version}/data/en_US/champion.json").json()

    for champ in champ_data["data"]:
        print(champ)
        champ_id = champ_data[champ]["id"]
        wget.download(f"https://ddragon.leagueoflegends.com/cdn/img/champion/centered/{champ_id}_0.jpg", out=f"{CACHE_DIRECTORY}/{game_version}/champion/{champ_id}_centered_splash.jpg")
        wget.download(f"https://ddragon.leagueoflegends.com/cdn/img/champion/loading/{champ_id}_0.jpg", out=f"{CACHE_DIRECTORY}/{game_version}/champion/{champ_id}_loading.jpg")
        wget.download(f"https://ddragon.leagueoflegends.com/cdn/img/champion/splash/{champ_id}_0.jpg", out=f"{CACHE_DIRECTORY}/{game_version}/champion/{champ_id}_splash.jpg")
        wget.download(f"https://ddragon.leagueoflegends.com/cdn/{game_version}/img/champion/{champ_id}.png", out=f"{CACHE_DIRECTORY}/{game_version}/champion/{champ_id}_square.png")

    pass

def dawe_game(nameKey, match_data: Match, PORT):
    if nameKey not in ws_manager:
        ws_manager[nameKey] = ConnectionManager()
    game_config = construct_config(nameKey, match_data.game_version, match_data.blue_team, match_data.red_team, match_data.tournament_logo)
    DaweDraft(nameKey, match_data.dawe_id, PORT, match_data.game_version, match_data.blue_team.players, match_data.red_team.players, game_config, ws_manager[nameKey],active_games[nameKey][1]).init()


if __name__ == '__main__':
    uvicorn.run("main:app",host='0.0.0.0', port=4557, reload=False, debug=True, workers=5)

