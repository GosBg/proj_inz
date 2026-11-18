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



# test działania wykryj widly
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

#---------reszta test

#----------podwójny szach----------
def wykryj_podwojny_szach(board, ruch):
    kolor = board.turn
    b = board.copy()
    b.push(ruch)
    if len(b.checkers()) >= 2:
        return kolor
    return None

#--------atak z odkrycia--------
def wykryj_atak_z_okrycia(board, ruch):
    """Ruch odsłonił linię własnej bierki (goniec/wieża/hetman) na króla
    albo figurę wroga (wartość >= 3), której wcześniej ta bierka nie atakowała."""
    kolor = board.turn
    przeciwnik = not kolor
    if board.is_castling(ruch):
        return None
    b = board.copy()
    b.push(ruch)
    for pole, bierka in b.piece_map().items():
        if bierka.color != przeciwnik:
            continue
        if bierka.piece_type != chess.KING and wartosci_bierek[bierka.piece_type] < 3:
            continue
        nowi = set(b.attackers(kolor, pole)) - set(board.attackers(kolor, pole))
        nowi.discard(ruch.to_square)   # bierka, która się ruszyła, to nie "odkrycie"
        if nowi:
            return kolor
    return None

# ---------- zwiazanie i szpikulec ----------
kierunki_prosto = [(1, 0), (-1, 0), (0, 1), (0, -1)]
kierunki_skos = [(1, 1), (1, -1), (-1, 1), (-1, -1)]

def pary_na_linii(b, pole, kolor):
    """Dla gońca/wieży/hetmana na 'pole': pary (A, B), gdzie A to najbliższa
    wroga bierka na linii, a B to druga wroga bierka tuż za nią."""
    figura = b.piece_at(pole)
    if figura.piece_type == chess.ROOK:
        kierunki = kierunki_prosto
    elif figura.piece_type == chess.BISHOP:
        kierunki = kierunki_skos
    elif figura.piece_type == chess.QUEEN:
        kierunki = kierunki_prosto + kierunki_skos
    else:
        return []

    pary = []
    for dx, dy in kierunki:
        plik, rzad = chess.square_file(pole), chess.square_rank(pole)
        znalezione = []
        while True:
            plik += dx
            rzad += dy
            if not (0 <= plik <= 7 and 0 <= rzad <= 7):
                break
            bierka = b.piece_at(chess.square(plik, rzad))
            if bierka is None:
                continue
            if bierka.color == kolor:   # własna bierka blokuje linię
                break
            znalezione.append(bierka)
            if len(znalezione) == 2:
                break
        if len(znalezione) == 2:
            pary.append((znalezione[0], znalezione[1]))
    return pary

def wykryj_zwiazanie(board, ruch):
    """Bliższa bierka A jest cenniejsza mniej niż B za nią (B to król lub cenniejsza figura)."""
    kolor = board.turn
    b = board.copy()
    b.push(ruch)
    if b.piece_at(ruch.to_square) is None:
        return None
    for A, B in pary_na_linii(b, ruch.to_square, kolor):
        if A.piece_type != chess.KING and wartosci_bierek[B.piece_type] > wartosci_bierek[A.piece_type]:
            return kolor
    return None

def wykryj_szpikulec(board, ruch):
    """Bliższa bierka A jest cenniejsza niż B za nią (B to figura, nie pion)."""
    kolor = board.turn
    b = board.copy()
    b.push(ruch)
    if b.piece_at(ruch.to_square) is None:
        return None
    for A, B in pary_na_linii(b, ruch.to_square, kolor):
        if wartosci_bierek[A.piece_type] > wartosci_bierek[B.piece_type] and wartosci_bierek[B.piece_type] >= 3:
            return kolor
    return None

# ---------- wisząca bierka ----------
def wiszace(board, kolor, min_wartosc=3):
    """Pola bierek koloru 'kolor' (poza królem), które można zbić z zyskiem:
    są atakowane i albo niebronione, albo atakowane przez tańszą bierkę."""
    wynik = []
    for pole, bierka in board.piece_map().items():
        if bierka.color != kolor or bierka.piece_type == chess.KING:
            continue
        wartosc = wartosci_bierek[bierka.piece_type]
        if wartosc < min_wartosc:
            continue
        napastnicy = board.attackers(not kolor, pole)
        if not napastnicy:
            continue
        najtanszy = min(wartosci_bierek[board.piece_type_at(p)] for p in napastnicy)
        obroncy = board.attackers(kolor, pole)
        if (not obroncy) or najtanszy < wartosc:
            wynik.append(pole)
    return wynik

def zbil_wiszaca(board, ruch):
    """Gracz zbił bierkę, która wisiała."""
    kolor = board.turn
    if not board.is_capture(ruch):
        return None
    if ruch.to_square in wiszace(board, not kolor):
        return kolor
    return None

def zostawil_wiszaca(board, ruch):
    """Po ruchu gracz ma własną wiszącą bierkę (kolor = ten, kto ją zostawił)."""
    kolor = board.turn
    b = board.copy()
    b.push(ruch)
    if wiszace(b, kolor):
        return kolor
    return None

# ---------- zbicie obrońcy ----------
def zbil_obroncy(board, ruch):
    """Zbita bierka broniła innej, która po zbiciu zaczęła wisieć (a wcześniej nie wisiała)."""
    kolor = board.turn
    przeciwnik = not kolor
    if not board.is_capture(ruch) or board.is_en_passant(ruch):
        return None
    zbity = ruch.to_square
    b = board.copy()
    b.push(ruch)
    przed = set(wiszace(board, przeciwnik))
    po = set(wiszace(b, przeciwnik))
    for pole in po - przed:
        if zbity in board.attackers(przeciwnik, pole):
            return kolor
    return None

# ---------- zbiorczo ----------
TAKTYKI = {
    "widly": wykryj_widly,
    "odkryty_atak": wykryj_atak_z_okrycia,
    "zwiazanie": wykryj_zwiazanie,
    "szpikulec": wykryj_szpikulec,
    "podwojny_szach": wykryj_podwojny_szach,
    "zbicie_wiszacej": zbil_wiszaca,
    "zostawil_wiszaca": zostawil_wiszaca,
    "zbicie_obroncy": zbil_obroncy,
}

def taktyki_ruchu(board, ruch):
    """Lista nazw taktyk zagranych tym ruchem. Zagrał je board.turn (przed ruchem)."""
    return [nazwa for nazwa, f in TAKTYKI.items() if f(board, ruch) is not None]

def przegapil(board, zagrany_ruch, wykrywacz):
    """Uniwersalne 'przegapił': była dostępna taktyka tego typu, a gracz jej nie zagrał."""
    dostepne = [r for r in board.legal_moves if wykrywacz(board, r) is not None]
    return bool(dostepne) and zagrany_ruch not in dostepne


# ---------- faza gry ----------
wartosci_figur_bez_pionow = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}

prog_otwarcie_ply = 20      # 10 pełnych ruchów
prog_koncowka_material = 26 # suma figur obu stron (start = 62)

def material_figur(board):
    """Suma wartości figur (bez pionów i króli) obu stron."""
    return sum(wartosci_figur_bez_pionow.get(b.piece_type, 0)
               for b in board.piece_map().values())

def faza_gry(board):
    """Zwraca 'otwarcie', 'gra_srodkowa' albo 'koncowka'. Wołaj na pozycji przed ruchem."""
    if material_figur(board) <= prog_koncowka_material:
        return "koncowka"
    if board.ply() < prog_otwarcie_ply:
        return "otwarcie"
    return "gra_srodkowa"

# ---------- pozycja otwarta / zamknięta ----------
def zablokowane_piony(board):
    """Liczba pionów (obu stron), które mają przed sobą pion wroga."""
    licznik = 0
    for pole, bierka in board.piece_map().items():
        if bierka.piece_type != chess.PAWN:
            continue
        przod = pole + (8 if bierka.color == chess.WHITE else -8)
        if 0 <= przod <= 63:
            cel = board.piece_at(przod)
            if cel is not None and cel.piece_type == chess.PAWN and cel.color != bierka.color:
                licznik += 1
    return licznik

def otwarte_linie(board):
    """Liczba linii bez żadnego piona."""
    linie_z_pionami = {chess.square_file(p) for p, b in board.piece_map().items()
                       if b.piece_type == chess.PAWN}
    return 8 - len(linie_z_pionami)

def wynik_zamkniecia(board):
    """0.0 = bardzo otwarta, 1.0 = bardzo zamknięta, ok. 0.5 = neutralna."""
    blokady = zablokowane_piony(board) / 16      # maks. 16 (8 par)
    otwarte = otwarte_linie(board) / 8
    return round((blokady + (1 - otwarte)) / 2, 3)

def czy_zamknieta(board, prog=0.6):
    return wynik_zamkniecia(board) >= prog
#----TESTY TUTAJ----
board = chess.Board("r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1")
print(przegapil_widly(board, chess.Move.from_uci("e1e2")))  
print(przegapil_widly(board, chess.Move.from_uci("d5c7")))  

testy = [
    ("4k3/8/8/8/4N3/8/8/4R1K1 w - - 0 1", "e4f6", wykryj_podwojny_szach, chess.WHITE),
    ("4k3/8/8/8/4N3/8/8/4R1K1 w - - 0 1", "e4c3", wykryj_atak_z_okrycia, chess.WHITE),
    ("4k3/8/8/8/4N3/8/8/4R1K1 w - - 0 1", "e1e2", wykryj_atak_z_okrycia, None),
    ("4k3/3n4/8/8/2B5/8/8/4K3 w - - 0 1", "c4b5", wykryj_zwiazanie, chess.WHITE),
    ("r5k1/8/8/q7/8/8/4K3/7R w - - 0 1", "h1a1", wykryj_szpikulec, chess.WHITE),
    ("4k3/8/8/3n4/8/8/3R4/4K3 w - - 0 1", "d2d5", zbil_wiszaca, chess.WHITE),
    ("6k1/4b3/2n5/1B6/8/8/8/4R1K1 w - - 0 1", "b5c6", zbil_obroncy, chess.WHITE),
]
for fen, uci, f, oczekiwane in testy:
    wynik = f(chess.Board(fen), chess.Move.from_uci(uci))
    print(f.__name__, uci, wynik, "OK" if wynik == oczekiwane else "BŁĄD")
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