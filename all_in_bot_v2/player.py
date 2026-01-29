'''
All-In Bot v2.1 - Variable pre-flop sizing to induce action
Changes from v2:
  4. Variable pre-flop raise sizing:
     - QQ+/trips: All-in (opponents fold but these are rare)
     - TT-JJ: Raise 6x BB to induce calls
     - 55-99/suited high: Raise 5x BB to induce calls

Previous changes (v2):
  1. Call small pre-flop raises (<=15) instead of always folding
  2. Larger post-flop bet sizing (~50% pot, min 4 chips)
  3. Defend overpairs and top pair against single bets
'''
from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction, DiscardAction
from skeleton.states import GameState, TerminalState, RoundState, NUM_ROUNDS, BIG_BLIND
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot

class Player(Bot):

    def __init__(self):
        self.rank_map = {r: i for i, r in enumerate("23456789TJQKA")}

    def handle_new_round(self, game_state, round_state, active):
        pass

    def handle_round_over(self, game_state, terminal_state, active):
        pass

    def get_action(self, game_state, round_state, active):
        legal = round_state.legal_actions()
        street = round_state.street
        my_cards = round_state.hands[active]
        board = round_state.board

        # ---------------------------------------------------------
        # 1. HANDLE DISCARD ACTION (Always required if legal)
        # ---------------------------------------------------------
        if DiscardAction in legal:
            return self.get_discard_action(my_cards, board)

        # ---------------------------------------------------------
        # 2. LOCKDOWN CHECK (Safety Mode)
        # ---------------------------------------------------------
        rounds_remaining = NUM_ROUNDS - game_state.round_num + 1
        secure_win_threshold = (rounds_remaining * 1.5) + 2

        if game_state.bankroll > secure_win_threshold:
            if CheckAction in legal:
                return CheckAction()
            return FoldAction()

        # ---------------------------------------------------------
        # 3. PRE-FLOP STRATEGY (Variable Sizing)
        # ---------------------------------------------------------
        if street == 0:
            my_pip = round_state.pips[active]
            opp_pip = round_state.pips[1 - active]
            continue_cost = opp_pip - my_pip

            hand_tier = self.get_preflop_tier(my_cards)

            if hand_tier > 0:  # We have a playable hand
                if RaiseAction in legal:
                    min_raise, max_raise = round_state.raise_bounds()

                    # TIER 1: QQ+ or Trips -> ALL-IN
                    if hand_tier == 1:
                        return RaiseAction(max_raise)

                    # TIER 2: TT-JJ -> Raise 6x BB (12 chips) to induce calls
                    elif hand_tier == 2:
                        raise_amount = min(max(min_raise, BIG_BLIND * 6), max_raise)
                        # If opponent already raised big, just go all-in
                        if continue_cost > 10:
                            return RaiseAction(max_raise)
                        return RaiseAction(raise_amount)

                    # TIER 3: 55-99 or suited high cards -> Raise 5x BB (10 chips)
                    else:  # hand_tier == 3
                        raise_amount = min(max(min_raise, BIG_BLIND * 5), max_raise)
                        # If opponent already raised big, just call or fold
                        if continue_cost > 15:
                            if CallAction in legal:
                                return CallAction()
                            return FoldAction()
                        return RaiseAction(raise_amount)

                if CallAction in legal:
                    return CallAction()
                if CheckAction in legal:
                    return CheckAction()
            else:
                # WEAK HAND STRATEGY

                # 1. If we can Check, just Check
                if CheckAction in legal:
                    return CheckAction()

                # 2. If facing a SMALL raise (<=15), call to see the flop
                #    This stops us bleeding chips to sophisticated raise-folders
                if CallAction in legal and continue_cost <= 15:
                    return CallAction()

                # 3. Facing a large raise or all-in -> Fold
                return FoldAction()

        # ---------------------------------------------------------
        # 4. POST-FLOP STRATEGY (Improved)
        # ---------------------------------------------------------
        my_pip = round_state.pips[active]
        opp_pip = round_state.pips[1 - active]
        pot_total = my_pip + opp_pip
        continue_cost = opp_pip - my_pip
        my_stack = round_state.stacks[active]

        # Evaluate our hand strength
        hand_strength = self.get_postflop_strength(my_cards, board)

        # FACING A BET
        if continue_cost > 0:
            # Check if we have a hand worth defending
            if hand_strength >= 0.50:  # Overpair, top pair, or better
                # Call one bet if it's not too large (<=50% of our stack)
                if continue_cost <= my_stack * 0.5:
                    if CallAction in legal:
                        return CallAction()

            # Weak hand or huge bet -> Fold
            return FoldAction()

        # WE CAN CHECK OR BET
        if CheckAction in legal:
            # Bet with decent hands for value
            if hand_strength >= 0.45 and RaiseAction in legal:
                min_raise, max_raise = round_state.raise_bounds()
                # Bet ~50% of pot, minimum 4 chips
                bet_size = max(4, int(pot_total * 0.5))
                bet_size = min(max(min_raise, bet_size), max_raise)
                return RaiseAction(bet_size)

            # Check with weak hands
            return CheckAction()

        # Fallback
        return FoldAction()

    def get_discard_action(self, my_cards, board):
        '''Smart discard: avoid giving opponent flush cards'''
        board_suits = [c[1] for c in board]

        flush_suit = None
        if len(board_suits) == 2 and board_suits[0] == board_suits[1]:
            flush_suit = board_suits[0]

        best_discard_index = 0
        lowest_danger_score = float('inf')

        for i, card in enumerate(my_cards):
            card_rank = self.rank_map[card[0]]
            card_suit = card[1]

            danger_score = card_rank

            if flush_suit and card_suit == flush_suit:
                danger_score += 100

            if danger_score < lowest_danger_score:
                lowest_danger_score = danger_score
                best_discard_index = i

        return DiscardAction(best_discard_index)

    def get_preflop_tier(self, cards):
        '''
        Returns hand tier for variable raise sizing:
        0 = Weak (fold or limp)
        1 = Premium (QQ+, trips) -> ALL-IN
        2 = Strong (TT-JJ) -> Raise 6x BB
        3 = Medium (55-99, suited high cards) -> Raise 5x BB
        '''
        ranks = [self.rank_map[c[0]] for c in cards]
        suits = [c[1] for c in cards]

        rank_counts = {}
        for r in ranks:
            rank_counts[r] = rank_counts.get(r, 0) + 1

        is_pair = False
        is_trips = False
        pair_rank = -1

        for r, count in rank_counts.items():
            if count == 2:
                is_pair = True
                pair_rank = r
            elif count == 3:
                is_trips = True

        # TIER 1: Trips or QQ+ (Q=10, K=11, A=12)
        if is_trips:
            return 1
        if is_pair and pair_rank >= 10:  # QQ+
            return 1

        # TIER 2: TT-JJ (T=8, J=9)
        if is_pair and pair_rank >= 8:  # TT-JJ
            return 2

        # TIER 3: 55-99 (5=3, 6=4, 7=5, 8=6, 9=7)
        if is_pair and pair_rank >= 3:  # 55-99
            return 3

        # TIER 3: Suited high cards (sum >= 25)
        if len(set(suits)) == 1:
            total_val = sum(r + 2 for r in ranks)
            if total_val >= 25:
                return 3

        # TIER 0: Weak hand
        return 0

    def get_postflop_strength(self, my_cards, board):
        '''
        Returns a strength score from 0.0 to 1.0
        Used to decide whether to bet/call post-flop
        '''
        all_cards = list(my_cards) + list(board)
        ranks = [self.rank_map[c[0]] for c in all_cards]
        suits = [c[1] for c in all_cards]
        my_ranks = [self.rank_map[c[0]] for c in my_cards]
        board_ranks = [self.rank_map[c[0]] for c in board] if board else []

        rank_counts = {}
        for r in ranks:
            rank_counts[r] = rank_counts.get(r, 0) + 1

        suit_counts = {}
        for s in suits:
            suit_counts[s] = suit_counts.get(s, 0) + 1

        # Check for flush (5+ of same suit)
        for count in suit_counts.values():
            if count >= 5:
                return 0.85

        # Check for quads
        for count in rank_counts.values():
            if count == 4:
                return 0.95

        # Check for full house
        has_trips = any(c >= 3 for c in rank_counts.values())
        has_pair = any(c == 2 for c in rank_counts.values())
        if has_trips and has_pair:
            return 0.90

        # Check for trips
        if has_trips:
            return 0.75

        # Check for straight
        sorted_ranks = sorted(set(ranks))
        for i in range(len(sorted_ranks) - 4):
            if sorted_ranks[i + 4] - sorted_ranks[i] == 4:
                return 0.80
        if set([0, 1, 2, 3, 12]).issubset(set(ranks)):  # Wheel
            return 0.80

        # Check for two pair
        pair_count = sum(1 for c in rank_counts.values() if c == 2)
        if pair_count >= 2:
            return 0.60

        # Check for one pair
        if pair_count == 1:
            pair_rank = [r for r, c in rank_counts.items() if c == 2][0]

            # Check if we made the pair (not just board pair)
            if pair_rank in my_ranks:
                max_board = max(board_ranks) if board_ranks else 0

                if pair_rank > max_board:
                    # OVERPAIR - very strong, defend this!
                    return 0.55 + (pair_rank / 12) * 0.15
                elif pair_rank == max_board:
                    # TOP PAIR - strong, worth defending
                    return 0.50 + (pair_rank / 12) * 0.10
                else:
                    # Middle/bottom pair
                    return 0.35 + (pair_rank / 12) * 0.10
            else:
                # Board paired, we don't have it
                return 0.25

        # High card only
        max_rank = max(my_ranks) if my_ranks else 0
        return 0.15 + (max_rank / 12) * 0.10


if __name__ == '__main__':
    run_bot(Player(), parse_args())
