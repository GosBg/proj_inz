from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import threading
import chess
import chess.engine
from pydantic import BaseModel
import uvicorn
import atexit

Katalog_podstawowy = Path("/run/media/blazej/wdblack sn770/projekt_inz/dane_pipeline/kod/chess")
lc0_path = Path("/run/media/blazej/wdblack sn770/projekt_inz/dane_pipeline/engines/lc0/build/release/lc0")
maia_path = Path("/run/media/blazej/wdblack sn770/projekt_inz/dane_pipeline/engines/maia/maia-1100.pb.gz")

maia = chess.engine.SimpleEngine.popen_uci([str(lc0_path), f"--weights={maia_path}"])
app = FastAPI()
maia_lock = threading.Lock()

@app.get("/")
def index():
    return FileResponse(Katalog_podstawowy / "chess.html")

class MaiaRequest(BaseModel):
    fen: str

@app.post("/api/maia")
def maia_move(req: MaiaRequest):
    board = chess.Board(req.fen)
    with maia_lock:
        result = maia.play(board, chess.engine.Limit(nodes=1))
    return {"move": result.move.uci()}

app.mount("/dane", StaticFiles(directory=Katalog_podstawowy / "dane"), name="dane")

atexit.register(maia.quit)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)