import zstandard
import chess.pgn
import io

input = "/run/media/blazej/wdblack sn770/projekt_inz/dane_pipeline/gry/lichess_db_standard_rated_2026-06.pgn.zst"
output = "/run/media/blazej/wdblack sn770/projekt_inz/dane_pipeline/gry/filtr_1100_rapid.pgn"

min_elo = 1050
max_elo = 1150
czas = "Rapid"
ilosc_gier = 1000

def stream_pgn(path):
    with open(path, "rb") as fh:
        dctx = zstandard.ZstdDecompressor()
        with dctx.stream_reader(fh) as reader:
            text_stream = io.TextIOWrapper(reader, encoding="utf-8")
            while True:
                game = chess.pgn.read_game(text_stream)
                if game is None:
                    break
                else:
                    yield game

def passes_filter(game):
    headers = game.headers
    try:
        white_elo = int(headers.get("WhiteElo", 0))
        black_elo = int(headers.get("BlackElo", 0))
    except ValueError:
        return False

    if not (min_elo <= white_elo <= max_elo):
        return False
    if not (min_elo <= black_elo <= max_elo):
        return False

    event = headers.get("Event", "")
    if czas not in event:
        return False

    # pomin jesli gra zosatła porzucona
    if headers.get("Termination", "") == "Abandoned":
        return False
    if headers.get("Result", "") not in ("1-0", "0-1", "1/2-1/2"):
        return False
    #jesli nic nie odrzucilo wczesniej to przechodzi
    return True

def main():
    count = 0
    with open(output, "w") as out:
        for game in stream_pgn(input):
            if passes_filter(game):
                out.write(str(game) + "\n\n")
                count += 1
                if count % 50 == 0:
                    print(f"Zebrano {count} gier...")
                if count >= ilosc_gier:
                    break
    print(f"Gotowe. Zebrano {count} gier -> {output}")

if __name__ == "__main__":
    main()