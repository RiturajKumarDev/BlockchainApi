from algopy import ARC4Contract, GlobalState, String, arc4


class FruitHash(ARC4Contract):
    def __init__(self) -> None:
        self.hash = GlobalState(String(""))

    @arc4.abimethod
    def store_hash(self, value: String) -> None:
        self.hash.value = value

    @arc4.abimethod
    def get_hash(self) -> String:
        return self.hash.value
