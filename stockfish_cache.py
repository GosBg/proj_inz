import chess
import chess.pgn
import chess.engine
import pandas as pd
import os
import time


stockfish_scieszka = "/usr/bin/stockfish" #bo mam na cały system 
plik_z_grami = "/run/media/blazej/wdblack sn770/projekt_inz/dane_pipeline/gry/filtr_1100_rapid.pgn"
plik_cache = "/run/media/blazej/wdblack sn770/projekt_inz/dane_pipeline/stockfish_cache/eval_v3.parquet"
glebokosc_analizy = 14
liczba_linii = 3

wartosci_bierek = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100,
}

def wczytaj_cache():
    if os.path.exists(plik_cache):
        df = pd.read_parquet(plik_cache)
        return {
           wiersz.fen:(wiersz.eval1, wiersz.eval2, wiersz.eval3)
           for wiersz in df.itertuples()
        }
    else:
        return{}

def zapisz_cache(cache):
    wiersze = [(fen, e[0], e[1], e[2]) for fen, e in cache.items()]
    df = pd.DataFrame(wiersze, columns=["fen", "eval1", "eval2", "eval3"])
    df.to_parquet(plik_cache)

def klucz_cache(board):
    # usuwamy licznik  polruchow i pelnych ruchow
    podzial = board.fen().split(" ")
    return " ".join(podzial[:4])

def eval_game(engine, board, cache):
    klucz = klucz_cache(board)
    if klucz in cache:
        return cache[klucz]
    else:
        info = engine.analyse(
            board,
            chess.engine.Limit(depth=glebokosc_analizy),
            multipv=liczba_linii
        )
        oceny = [linia["score"].relative.score(mate_score=10000) for linia in info]
        # jesli mniej niz 3 legalne posuniecia do wolnych dajemy None
        while len(oceny) < liczba_linii:
            oceny.append(None)
        wynik = tuple(oceny)
        cache[klucz] = wynik
        return wynik

def partia(engine, cache, max_games=None):
    with open(plik_z_grami) as f:
        licznik_partii = 0
        while True:
            gra = chess.pgn.read_game(f)
            if gra is None:
                break

            board = gra.board()
            for ruch in gra.mainline_moves():
                eval_game(engine, board, cache)
                board.push(ruch)
            eval_game(engine, board, cache)

            licznik_partii += 1 
            if licznik_partii % 10 == 0:
                print(f"Preszło {licznik_partii} gier, rozmiar {len(cache)}")
                zapisz_cache(cache)

            if max_games and licznik_partii >= max_games:
                break

        zapisz_cache(cache)
        print(f"gotowe")



# test działania wykryj fork
def wykryj_widly(board, ruch, tylko_bezpieczne=False):
    kolor = board.turn
    przeciwnik = not kolor

    b = board.copy()
    b.push(ruch)

    pole = ruch.to_square
    figura = b.piece_at(pole)
    if figura is None or figura.piece_type == chess.KING:
        return None

    if tylko_bezpieczne:
        bijacy = b.attackers(przeciwnik, pole)
        if bijacy:
            najtanszy = min(wartosci_bierek[b.piece_type_at(p)] for p in bijacy)
            jest_bronione = bool(b.attackers(kolor, pole))
            if (not jest_bronione) or najtanszy < wartosci_bierek[figura.piece_type]:
                return None

    cele = 0
    for pole_celu in b.attacks(pole):
        cel = b.piece_at(pole_celu)
        if cel is None or cel.color != przeciwnik:
            continue
        niebronione = not b.attackers(przeciwnik, pole_celu)
        if (cel.piece_type == chess.KING
                or wartosci_bierek[cel.piece_type] > wartosci_bierek[figura.piece_type]
                or niebronione):
            cele += 1

    if cele >= 2:
        return kolor
    return None

kolor_forkujacego = wykryj_widly(board, ruch)
if kolor_forkujacego is not None:
   zagral_fork = kolor_forkujacego        
   dostal_fork = not kolor_forkujacego 

def widly_dostepne(board):
    """Lista ruchów, które są forkiem dla strony na ruchu."""
    return [r for r in board.legal_moves
            if wykryj_widly(board, r, tylko_bezpieczne=True) is not None]

def przegapil_widly(board, zagrany_ruch):
    dostepne = widly_dostepne(board)
    if not dostepne:
        return False
    return zagrany_ruch not in dostepne

board = chess.Board("r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1")
print(przegapil_widly(board, chess.Move.from_uci("e1e2")))  # True: Nc7+ was available
print(przegapil_widly(board, chess.Move.from_uci("d5c7")))  # False: played it
def main():
    cache = wczytaj_cache()
    engine = chess.engine.SimpleEngine.popen_uci(stockfish_scieszka)
    engine.configure({"Threads": 4, "Hash": 512})
    try:
        start = time.time()
        partia(engine, cache, max_games=250)#50 na test
        print(f"Czas: {time.time() - start:.1f} s")
    finally:
        engine.quit()

if __name__ == "__main__":
    main()