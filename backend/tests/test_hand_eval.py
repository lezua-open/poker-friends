from app.game.hand_eval import best_hand


def test_straight_flush_beats_quads():
    straight_flush = best_hand(["AS", "KS", "QS", "JS", "TS", "2C", "3D"])
    quads = best_hand(["AH", "AS", "AD", "AC", "9S", "2C", "3D"])
    assert straight_flush > quads


def test_wheel_straight():
    wheel = best_hand(["AS", "2D", "3C", "4H", "5S", "9D", "TD"])
    six_high = best_hand(["2S", "3D", "4C", "5H", "6S", "9D", "TD"])
    assert six_high > wheel

