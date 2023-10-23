import beaker
import pyteal as pt
from pytealext import Max, Min

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
    player_cards = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )
    player_min_total = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )
    player_max_total = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )
    request = beaker.GlobalStateValue(
        stack_type=pt.TealType.bytes,
    )
    action_timer = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )
    bank_cards = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )
    bank_min_total = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )
    bank_max_total = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
    )
    winner = beaker.GlobalStateValue(
        stack_type=pt.TealType.bytes,
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


@beaker.pyteal.Subroutine(pt.TealType.uint64)
def card_value(id):
    """
    Get a card value from its ID
    id: ID of the card of which the value will be returned
    """
    return pt.Seq(
        Min(id % pt.Int(13) + pt.Int(1), pt.Int(10))
    )


@beaker.pyteal.Subroutine(pt.TealType.uint64)
def sig_to_card_pos(sig: pt.abi.DynamicBytes):
    """
    Get the card position corresponding to a signature
    sig: signature by the bank of a request
    """
    return pt.Seq(
        pt.Btoi(pt.BytesMod(
            sig.get(), pt.Extract(pt.Itob(appState.cards_left.get()), pt.Int(7), pt.Int(1))
        ))
    )


@beaker.pyteal.Subroutine(pt.TealType.none)
def give_card_to_player(pos):
    """
    Give a card to the player
    pos: index of the card to be popped in the remaining card array
    """
    card = pt.ScratchVar(pt.TealType.uint64)
    mint_value = pt.ScratchVar(pt.TealType.uint64)
    max_value = pt.ScratchVar(pt.TealType.uint64)
    return pt.Seq(
        card.store(pop_card(pos, pt.Int(1))),
        appState.player_cards.set(appState.player_cards.get() + pt.Int(1)),
        mint_value.store(card_value(card.load())),
        max_value.store(
            pt.If(
                mint_value.load() == pt.Int(1)
            ).Then(
                pt.Int(11)
            ).Else(
                mint_value.load()
            )
        ),
        appState.player_min_total.set(
            appState.player_min_total.get() + mint_value.load()),
        appState.player_max_total.set(
            appState.player_max_total.get() + max_value.load()),
    )


@beaker.pyteal.Subroutine(pt.TealType.none)
def give_card_to_bank(pos):
    """
    Give a card to the bank
    pos: index of the card to be popped in the remaining card array
    """
    card = pt.ScratchVar(pt.TealType.uint64)
    min_value = pt.ScratchVar(pt.TealType.uint64)
    max_value = pt.ScratchVar(pt.TealType.uint64)
    return pt.Seq(
            card.store(pop_card(pos, pt.Int(2))),
            appState.bank_cards.set(appState.bank_cards.get() + pt.Int(1)),
            min_value.store(card_value(card.load())),
            max_value.store(
                pt.If(
                    min_value.load() == pt.Int(1)
                ).Then(
                    pt.Int(11)
                ).Else(
                    min_value.load()
                )
            ),
            appState.bank_min_total.set(appState.bank_min_total.get() + min_value.load()),
            appState.bank_max_total.set(appState.bank_max_total.get() + max_value.load()),
        )


@app.external
def distribute_req(request: pt.abi.DynamicBytes):
    """
    Callable by the player to randomly choose a card to distribute in the initial phase.
    request: JSON containing a (`nonce` = appState.nonce), a (`app` = Global.current_application_id()) and a random `nonce_p`
    """
    return pt.Seq(
        pt.Assert(
            appState.state.get() == DISTRIBUTE,
            pt.Txn.sender() == pt.Global.creator_address(),
            pt.JsonRef.as_uint64(request.get(), pt.Bytes("nonce")) == appState.nonce.get(),
            pt.JsonRef.as_uint64(request.get(), pt.Bytes("app")) == pt.Global.current_application_address(),
        ),
        appState.request.set(request.get()),
        appState.nonce.set(appState.nonce.get() + pt.Int(1)),
        appState.state.set(DISTRIBUTE_ACT),
        appState.action_timer.set(pt.Global.round()),
    )


@app.external
def distribute_act(sig: pt.abi.DynamicBytes):
    return pt.Seq(
        pt.OpUp(pt.OpUpMode.OnCall).maximize_budget(pt.Int(5000)),
        pt.Assert(
            appState.state.get() == DISTRIBUTE_ACT,
            pt.Ed25519Verify(
                appState.request.get(),
                sig.get(),
                appState.bank.get(),
            )
        ),
        pt.If(appState.player_cards.get() < pt.Int(2)).Then(
            give_card_to_player(sig_to_card_pos(sig)),
        ).Else (
            give_card_to_bank(sig_to_card_pos(sig)),
        ),
        # If distribution finished and player has blackjack (player cannot hit)
        pt.If(
            pt.And(
                appState.bank_cards.get() == pt.Int(1),
                appState.player_max_total.get() == pt.Int(21),
            )
        ).Then(
            appState.state.set(BANK)
        ).ElseIf(
            # If distribution finished and player does not have (player can hit)
            pt.And(
                appState.bank_cards.get() == pt.Int(1),
                appState.player_max_total.get() != pt.Int(21),
            )
        ).Then(
            appState.state.set(PLAYER)
        ).Else(
            appState.state.set(DISTRIBUTE),
        ),
        appState.action_timer.set(pt.Global.round()),
    )


@app.external
def hit_req(request: pt.abi.DynamicBytes):
    """
    Callable by the player to randomly choose a card to draw.
    request: JSON containing a (`nonce` = appState.nonce), a (`app` = Global.current_application_id()) and a random `nonce_p`
    """
    return pt.Seq(
        pt.Assert(
            appState.state.get() == PLAYER,
            
            pt.Txn.sender() == pt.Global.creator_address(),
            pt.JsonRef.as_uint64(request.get(), pt.Bytes("nonce")) == appState.nonce.get(),
            pt.JsonRef.as_uint64(request.get(), pt.Bytes("app")) == pt.Global.current_application_id(),
        ),
        
        appState.request.set(request.get()),
        appState.nonce.set(appState.nonce.get() + pt.Int(1)),

        appState.state.set(HIT_ACT),
        appState.action_timer.set(pt.Global.round()),
    )


@app.external
def hit_act(sig: pt.abi.DynamicBytes):
    """
    Callable by the bank to specify what card will be drawn by the player.
    sig: signature of appState.request by appState.bank
    """
    return pt.Seq(
        pt.OpUp(pt.OpUpMode.OnCall).maximize_budget(pt.Int(5000)),
        pt.Assert(
            appState.state.get() == HIT_ACT,
            pt.Ed25519Verify(appState.request.get(), sig.get(), appState.bank.get()),
        ),
        
        appState.give_card_to_player(appState.sig_to_card_pos(sig)),
        
        # If player busted and does not have aces worth 11 (bank wins)
        pt.If(pt.And(
            appState.player_max_total.get() > pt.Int(21), 
            appState.player_max_total.get() == appState.player_min_total.get())
        ).Then(
            appState.state.set(FINISH),
            appState.winner.set(appState.bank.get()),
        # If player busted BUT has at least one ace worth 11 (make ace worth one)
        ).ElseIf(
            pt.And(
                appState.player_max_total.get() > pt.Int(21), 
                appState.player_max_total.get() != appState.player_min_total.get())
        ).Then(
            appState.state.set(PLAYER),
            appState.player_max_total.set(appState.player_max_total.get() - pt.Int(10)),
        # If a player reached 21 (cannot hit again)
        ).ElseIf(
            appState.player_max_total.get() == pt.Int(21)
        ).Then(
            appState.state.set(BANK),
        # If a player is below 21 (can hit again)
        ).Else(
            appState.state.set(PLAYER),
        ),
        appState.action_timer.set(pt.Global.round()),
    )


@app.external
def stand_req(request: pt.abi.DynamicBytes):
    """
    Callable by the player to randomly choose a card to let the bank draw.
    request: JSON containing a (`nonce` = appState.nonce), a (`app` = Global.current_application_id()) and a random `nonce_p`
    """
    return pt.Seq(
        pt.Assert(
            pt.Or(
                appState.state.get() == PLAYER,
                appState.state.get() == BANK,
            ),
            
            pt.Txn.sender() == pt.Global.creator_address(),
            pt.JsonRef.as_uint64(request.get(), pt.Bytes("nonce")) == appState.nonce.get(),
            pt.JsonRef.as_uint64(request.get(), pt.Bytes("app")) == pt.Global.current_application_id(),
        ),
        
        appState.request.set(request.get()),
        appState.nonce.set(appState.nonce.get() + pt.Int(1)),
        
        appState.state.set(STAND_ACT),
        appState.action_timer.set(pt.Global.round()),
    )


@app.external
def stand_act(sig: pt.abi.DynamicBytes):
    """
    Callable by the bank to specify what card will be drawn by the bank.
    sig: signature of appState.request by appState.bank
    """
    return pt.Seq(
        pt.OpUp(pt.OpUpMode.OnCall).maximize_budget(pt.Int(5000)),
        pt.Assert(
            appState.state.get() == STAND_ACT,
            pt.Ed25519Verify(appState.request.get(), sig.get(), appState.bank.get()),
        ),
        
        appState.give_card_to_bank(appState.sig_to_card_pos(sig)),
        
        # If bank busted and does not have aces worth 11 (player wins)
        pt.If(
            pt.And(
                appState.bank_max_total.get() > pt.Int(21), 
                appState.bank_max_total.get() == appState.bank_min_total.get())
            ).Then(
                pt.Seq(
                    appState.state.set(FINISH),
                    appState.winner.set(pt.Global.creator_address()
                ),
        # If bank busted BUT has at least one ace worth 11 (make ace worth one)
        )).ElseIf(
            pt.And(
                appState.bank_max_total.get() > pt.Int(21), 
                appState.bank_max_total.get() != appState.bank_min_total.get())
            ).Then(
                appState.state.set(BANK),
                appState.bank_max_total.set(appState.bank_max_total.get() - pt.Int(10))
        # If bank reached a hand worth at least 17 (game is over)
        ).ElseIf(appState.bank_max_total.get() >= pt.Int(17)).Then(
            # If bank's total is higher than player (bank wins)
            pt.If(appState.bank_max_total.get() > appState.player_max_total.get()).Then(
                win_bank(),
            # If bank's total is higher than player (player wins)
            ).ElseIf(appState.bank_max_total.get() < appState.player_max_total.get()).Then(
                win_player(),
            # If bank's total is the same as player
            ).Else(
                # If player has black jack (player wins)
                pt.If(
                    pt.And(
                        appState.player_max_total.get() == pt.Int(21), 
                        appState.player_cards.get() == pt.Int(2), 
                        appState.bank_cards.get() != pt.Int(2)
                    )
                ).Then(
                    win_player(),
                # If bank has black jack (bank wins)
                ).ElseIf(
                    pt.And(
                        appState.player_max_total.get() == pt.Int(21), 
                        appState.player_cards.get() != pt.Int(2), 
                        appState.bank_cards.get() == pt.Int(2)
                    )
                ).Then(
                    win_bank(),
                # If neither has black jack (push/draw)
                ).Else(
                    push(),
                )
            )
        # If bank has not reached 17 yet (continue drawing cards)
        ).Else(
            appState.state.set(BANK),
        ),
        
        appState.action_timer.set(pt.Global.round()),
    )

def finish():
    """
    Callable by the winner to get all the funds
    """
    return pt.Seq(
        pt.Assert(
            appState.winner.get() == pt.Txn.sender()
        ),
        
        pt.If(appState.winner.get() == appState.bank.get()).Then(
            give_funds_caller(pt.Int(0))
        ).Else(
            give_funds_caller(pt.Int(1))
        )
    )

@beaker.pyteal.Subroutine(pt.TealType.none)
def win_bank():
    return pt.Seq(
        appState.state.set(FINISH),
        appState.winner.set(appState.bank.get())
    )


@beaker.pyteal.Subroutine(pt.TealType.none)
def win_player():
    return pt.Seq(
        appState.state.set(FINISH),
        appState.winner.set(pt.Global.creator_address())
    )

@beaker.pyteal.Subroutine(pt.TealType.none)
def push():
    return pt.Seq(
        appState.state.set(PUSH),
    )

@app.external
def forfeit():
    """
    Callable by either the bank or the player if the other stops interacting.
    """
    return pt.Seq(
        pt.Assert(pt.Or(
            pt.And(
                pt.Or(
                    appState.state.get() == PLAYER,
                    appState.state.get() == BANK,
                ), 
                pt.Txn.sender() == appState.bank.get(),
            ),
            pt.And(
                pt.Or(
                    appState.state.get() == HIT_ACT,
                    appState.state.get() == STAND_ACT,
                ),
                pt.Txn.sender() == pt.Global.creator_address(),
            ),
            appState.action_timer.get() + TIMEOUT <= pt.Global.round(),
        )),
        appState.state.set(FINISH),
        appState.winner.set(pt.Txn.sender())
    )

@app.delete
def delete(asset: pt.abi.Asset, other: pt.abi.Account, fee_holder: pt.abi.Account):
        """
        Routes the finish, cancel and push methods
        creator: reference to opponent's address, if existing (used to enable InnerTxn)
        fee_holder: reference to appState.fee_holder (used to enable InnerTxn)
        asset: reference to appState.asset (used to enable InnerTxn)
        """
        return pt.Seq(
            pt.Assert(
                asset.asset_id() == appState.asset.get(),
                pt.If(
                    pt.Txn.sender() == pt.Global.creator_address()
                ).Then(
                    other.address() == appState.bank.get()
                ).Else(
                    other.address() == pt.Global.creator_address()
                ),
                fee_holder.address() == appState.fee_holder.get(),
            ),
            pt.If(appState.state.get() == FINISH).Then(
                appState.finish()
            ).ElseIf(appState.state.get() == WAIT).Then(
                appState.cancel()
            ).ElseIf(appState.state.get() == PUSH).Then(
                appState.give_funds_back()
            ).Else(
                pt.Err()
            )
        )


def cancel():
    """
    Callable by the creator if the bank failed to join, to cancel the game
    """
    return pt.Seq(
        pt.Assert(
            pt.Txn.sender() == pt.Global.creator_address(),
            appState.state.get() == WAIT,
        ),
        give_funds_caller(pt.Int(0)),
    )

def finish(self):
    """
    Callable by the winner to get all the funds
    """
    return pt.Seq(
        pt.Assert(
            appState.winner.get() == pt.Txn.sender()
        ),
        
        pt.If(self.winner.get() == self.bank.get()).Then(
            give_funds_caller(pt.Int(0))
        ).Else(
            give_funds_caller(pt.Int(1))
        )
    )


@beaker.pyteal.Subroutine(pt.TealType.none)
def give_funds_back():
    """
    Give the funds back to the bank and the player
    """
    return pt.Seq(
        pt.InnerTxnBuilder.Begin(),
        pt.InnerTxnBuilder.SetFields({
            pt.TxnField.type_enum: pt.TxnType.AssetTransfer,
            pt.TxnField.xfer_asset: appState.asset.get(),
            pt.TxnField.asset_amount: appState.stake.get(),
            pt.TxnField.asset_receiver: pt.Global.creator_address(),
        }),
        pt.InnerTxnBuilder.Next(),
        pt.InnerTxnBuilder.SetFields({
            pt.TxnField.type_enum: pt.TxnType.AssetTransfer,
            pt.TxnField.xfer_asset: appState.asset.get(),
            pt.TxnField.asset_close_to: appState.bank.get(),
        }),
        pt.InnerTxnBuilder.Next(),
        pt.InnerTxnBuilder.SetFields({
            pt.TxnField.type_enum: pt.TxnType.Payment,
            pt.TxnField.close_remainder_to: pt.Global.creator_address(),
        }),
        pt.InnerTxnBuilder.Submit(),
    )


@beaker.pyteal.Subroutine(pt.TealType.none)
def give_funds_caller(pay_fee):
    """
    Give all the funds to the caller 
    pay_fee: specifies if a part of the funds will be paid as fee
    """
    return pt.Seq(
        pt.InnerTxnBuilder.Begin(),
        pt.If(pay_fee).Then(pt.Seq(
            pt.InnerTxnBuilder.SetFields({
                pt.TxnField.type_enum: pt.TxnType.AssetTransfer,
                pt.TxnField.xfer_asset: appState.asset.get(),
                pt.TxnField.asset_amount: appState.stake.get() / appState.fee_amount.get(),
                pt.TxnField.asset_receiver: appState.fee_holder.get(),
            }),
            pt.InnerTxnBuilder.Next(),
        )),
        pt.InnerTxnBuilder.SetFields({
            pt.TxnField.type_enum: pt.TxnType.AssetTransfer,
            pt.TxnField.xfer_asset: appState.asset.get(),
            pt.TxnField.asset_close_to: pt.Txn.sender(),
        }),
        pt.InnerTxnBuilder.Next(),
        pt.InnerTxnBuilder.SetFields({
            pt.TxnField.type_enum: pt.TxnType.Payment,
            pt.TxnField.close_remainder_to: pt.Global.creator_address(),
        }),
        pt.InnerTxnBuilder.Submit(),
    )


@app.external
def hello(name: pt.abi.String, *, output: pt.abi.String) -> pt.Expr:
    return output.set(pt.Concat(pt.Bytes("Hello, "), name.get()))
