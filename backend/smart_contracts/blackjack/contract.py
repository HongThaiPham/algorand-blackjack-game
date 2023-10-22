import beaker
import pyteal as pt

action_timeout = 10

state_init = 0
state_poor = 1
state_wait = 2
state_distribute = 3
state_distribute_act = 4
state_player = 5
state_hit_act = 6
state_bank = 7
state_stand_act = 8
state_finish = 9
state_push = 10


# Configuring
# Contract created
INIT = pt.Int(state_init)
# Contract address initialized without stake
POOR = pt.Int(state_poor)
# Creator decided the stake and is waiting for the bank
WAIT = pt.Int(state_wait)
# Play
# Phase in which the first 3 cards are given (2 to the player, 1 to the bank)
DISTRIBUTE = pt.Int(state_distribute)
DISTRIBUTE_ACT = pt.Int(state_distribute_act)
# State in which the player can decide if to hit or to stand
PLAYER = pt.Int(state_player)
# State in which the bank must reveal the card that the player will draw
HIT_ACT = pt.Int(state_hit_act)
# State in which the player can only stand
BANK = pt.Int(state_bank)
# State in which the bank must reveal the card that they will draw
STAND_ACT = pt.Int(state_stand_act)

# End of the game
# Someone won (specified by winner)
FINISH = pt.Int(state_finish)
# Draw
PUSH = pt.Int(state_push)

"""
Other params
"""
WINNING_SCORE = pt.Int(2)
TIMEOUT = pt.Int(action_timeout)


class AppState:
    asset = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )
    bank = beaker.GlobalStateValue(
        stack_type=pt.TealType.bytes,
    )
    fee_holder = beaker.GlobalStateValue(
        stack_type=pt.TealType.bytes,
    )
    cards = beaker.GlobalStateValue(
        stack_type=pt.TealType.bytes,
    )
    cards_left = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )
    nonce = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )
    state = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )
    stake = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )
    fee_amount = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )
    action_timer = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )
    last_card = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )


appState = AppState()
app = beaker.Application("blackjack", state=appState)


@app.create
def create(asset: pt.abi.Asset, bank: pt.abi.Account, fee_holder: pt.abi.Account) -> pt.Expr:
    return pt.Seq(
        appState.asset.set(asset.asset_id()),
        appState.bank.set(bank.address()),
        appState.fee_holder.set(fee_holder.address()),
        appState.cards.set(pt.Bytes(b"\x00"*52)),
        appState.cards_left.set(pt.Int(52)),
        appState.nonce.set(pt.Int(0)),
        appState.state.set(INIT),
    )


@app.opt_in
def opt_in(txn: pt.abi.AssetTransferTransaction, fee_amount: pt.abi.Uint64) -> pt.Expr:
    return pt.If(appState.state.get() == POOR).Then(
        define_stake(txn, fee_amount)
    ).ElseIf(appState.state.get() == WAIT).Then(
        join_server(txn, fee_amount)
    ).Else(
        pt.Err()
    )


def define_stake(txn: pt.abi.AssetTransferTransaction, fee_amount: pt.abi.Uint64):
    return pt.Seq(
        pt.Assert(
            appState.state.get() == POOR,
            pt.Txn.sender() == pt.Global.creator_address(),
            txn.get().xfer_asset() == appState.asset.get(),
            txn.get().asset_receiver() == pt.Global.current_application_address(),
        ),
        appState.stake.set(txn.get().asset_amount()),
        appState.fee_amount.set(fee_amount.get()),
        appState.state.set(WAIT),
    )


def join_server(txn: pt.abi.AssetTransferTransaction, fee_amount: pt.abi.Uint64):
    return pt.Seq(
        pt.Assert(
            appState.state.get() == WAIT,
            pt.Txn.sender() == appState.bank.get(),
            txn.get().xfer_asset() == appState.asset.get(),
            txn.get().asset_receiver() == pt.Global.current_application_address(),
            txn.get().asset_amount() == appState.stake.get(),
        ),
        appState.fee_amount.set(fee_amount.get()),
        appState.state.set(DISTRIBUTE),
        appState.action_timer.set(pt.Global.round()),
    )


# To initialize the application account the creator of the smart contract has pay the fees of the contract and the minimum balance.


@app.external
def init(txn: pt.abi.PaymentTransaction, asset: pt.abi.Asset):
    return pt.Seq(
        pt.Assert(
            appState.state.get() == INIT,
            pt.Txn.sender() == pt.Global.creator_address(),
            txn.get().amount() == pt.Int(1000000),
            asset.asset_id() == appState.asset.get(),
        ),
        pt.InnerTxnBuilder.Begin(),
        pt.InnerTxnBuilder.SetFields(
            {
                pt.TxnField.type_enum: pt.TxnType.AssetTransfer,
                pt.TxnField.asset_receiver: pt.Global.current_application_address(),
                pt.TxnField.xfer_asset: appState.asset.get(),
                pt.TxnField.asset_amount: pt.Int(0),
            },
        ),
        pt.InnerTxnBuilder.Submit(),
        appState.state.set(POOR),
    )


# In order for the player or the bank to receive a card, it must be removed from the deck. To do this you need to provide the id of the card and which player it was drawn by.
@beaker.pyteal.Subroutine(pt.TealType.uint64)
def pop_card(pos, pop_id):
    """
    Remove a card from the deck and returns its ID
    pos: index of the card to be popped in the remaining card array
    pop_id: id that encodes why the card has been popped (0 unpopped, 1 player, 2 bank)
    """
    i = pt.ScratchVar(pt.TealType.uint64)
    j = pt.ScratchVar(pt.TealType.uint64)
    return pt.Seq(
        pt.For(
            pt.Seq(
                i.store(pt.Int(0)),
                j.store(pt.Int(0)),
            ),
            j.load() <= pos,
            i.store(i.load() + pt.Int(1)),
        ).Do(
            pt.Seq(
                pt.If(
                    pt.GetByte(appState.cards.get(), i.load()) == pt.Int(0)
                ).Then(
                    j.store(j.load() + pt.Int(1)),
                ),
            ),

        ),
        i.store(i.load() - pt.Int(1)),
        appState.cards.set(pt.SetByte(
            appState.cards.get(), i.load(), pop_id)),
        appState.cards_left.set(appState.cards_left.get() - pt.Int(1)),
        appState.last_card.set(i.load()),
        i.load()
    )


@app.external
def hello(name: pt.abi.String, *, output: pt.abi.String) -> pt.Expr:
    return output.set(pt.Concat(pt.Bytes("Hello, "), name.get()))
