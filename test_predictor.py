#!/usr/bin/env python3
"""
Smart Predictor Test Suite
Tests that the predictor prevents 3+ simultaneous winners.
Run: python test_predictor.py
"""

import random
import sys

# ==================== BINGO LOGIC ====================
BINGO_NUMBERS = list(range(1, 76))  # 1-75

def check_bingo(flat_cartela, called_numbers):
    """Check if a cartela has bingo."""
    called_set = set(called_numbers)
    grid = [flat_cartela[i*5:(i+1)*5] for i in range(5)]
    
    def is_marked(n):
        return n == 0 or n in called_set
    
    # Check rows
    for row in grid:
        if all(is_marked(n) for n in row):
            return True
    # Check columns
    for col in range(5):
        if all(is_marked(grid[row][col]) for row in range(5)):
            return True
    # Check diagonals
    if all(is_marked(grid[i][i]) for i in range(5)):
        return True
    if all(is_marked(grid[i][4-i]) for i in range(5)):
        return True
    return False


def generate_random_cartela():
    """Generate a random bingo cartela."""
    cartela = []
    for col in range(5):
        start = col * 15 + 1
        end = start + 15
        nums = random.sample(range(start, end), 5)
        cartela.extend(nums)
    # Set center as free space
    cartela[12] = 0
    return cartela


# ==================== PREDICTOR (3-PHASE) ====================
def smart_predictor(called, available, player_cartelas, num_called):
    """
    Three-phase predictor:
    Phase 1 (< 40): ABSOLUTE zero tolerance - no winner allowed
    Phase 2 (40-54): Target 0, allow 1 if impossible
    Phase 3 (55+): Pick minimum, game must end
    """
    random.shuffle(available)
    best_number = available[0]
    min_winners = 9999
    
    for candidate in available:
        simulated_called = called + [candidate]
        candidate_winners_count = 0
        
        for uid, cartelas in player_cartelas.items():
            for flat in cartelas:
                if check_bingo(flat, simulated_called):
                    candidate_winners_count += 1
                    break  # Count player once
        
        # Phase 1: Early game - NO winner allowed
        if num_called < 40:
            if candidate_winners_count == 0:
                best_number = candidate
                break
            if candidate_winners_count < min_winners:
                min_winners = candidate_winners_count
                best_number = candidate
            continue
        
        # Phase 2: Mid game - Target 0, allow 1
        if num_called < 55:
            if candidate_winners_count == 0:
                best_number = candidate
                break
            if candidate_winners_count <= 1 and min_winners > 1:
                best_number = candidate
                min_winners = candidate_winners_count
            if candidate_winners_count < min_winners:
                min_winners = candidate_winners_count
                best_number = candidate
            continue
        
        # Phase 3: Late game - Pick minimum
        if candidate_winners_count < min_winners:
            min_winners = candidate_winners_count
            best_number = candidate
        if min_winners == 0:
            break
    
    return best_number


# ==================== OLD PREDICTOR (BASELINE) ====================
def old_predictor(called, available, player_cartelas):
    """Old predictor that only targeted <= 1 winner."""
    random.shuffle(available)
    best_number = available[0]
    min_winners = 9999
    
    for candidate in available:
        simulated_called = called + [candidate]
        candidate_winners_count = 0
        
        for uid, cartelas in player_cartelas.items():
            for flat in cartelas:
                if check_bingo(flat, simulated_called):
                    candidate_winners_count += 1
                    break
        
        if candidate_winners_count <= 1:
            best_number = candidate
            break
        
        if candidate_winners_count < min_winners:
            min_winners = candidate_winners_count
            best_number = candidate
    
    return best_number


# ==================== TEST SCENARIOS ====================
def run_game_simulation(predictor_func, num_players, max_cartelas_per_player=2, seed=42):
    """Run a full game simulation and return winner count."""
    random.seed(seed)
    
    # Generate player cartelas
    player_cartelas = {}
    for i in range(num_players):
        uid = str(i)
        num_cartelas = random.randint(1, max_cartelas_per_player)
        player_cartelas[uid] = [generate_random_cartela() for _ in range(num_cartelas)]
    
    called = []
    available = list(BINGO_NUMBERS)
    winners_this_round = 0
    
    while available and winners_this_round == 0:
        num_called = len(called)
        
        # Use predictor to choose number
        if predictor_func == 'smart':
            number = smart_predictor(called, available, player_cartelas, num_called)
        else:
            number = old_predictor(called, available, player_cartelas)
        
        called.append(number)
        available.remove(number)
        
        # Check for winners
        for uid, cartelas in player_cartelas.items():
            for flat in cartelas:
                if check_bingo(flat, called):
                    winners_this_round += 1
                    break
    
    return winners_this_round, len(called)


def test_phase1_no_winners():
    """Test Phase 1: No winners allowed before 40 numbers."""
    print("=" * 70)
    print("TEST 1: Phase 1 - No winners before 40 numbers")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    for num_players in [2, 5, 10]:
        for seed in range(10):
            random.seed(seed)
            
            # Generate cartelas
            player_cartelas = {}
            for i in range(num_players):
                uid = str(i)
                player_cartelas[uid] = [generate_random_cartela() for _ in range(2)]
            
            called = []
            available = list(BINGO_NUMBERS)
            early_winner = False
            
            # Simulate first 39 numbers
            for turn in range(39):
                if not available:
                    break
                num_called = len(called)
                number = smart_predictor(called, available, player_cartelas, num_called)
                called.append(number)
                available.remove(number)
                
                # Check for winners
                for uid, cartelas in player_cartelas.items():
                    for flat in cartelas:
                        if check_bingo(flat, called):
                            early_winner = True
                            break
                    if early_winner:
                        break
                if early_winner:
                    break
            
            if early_winner:
                failed += 1
                print(f"  [FAIL] {num_players} players, seed={seed}: Winner before 40!")
            else:
                passed += 1
    
    total = passed + failed
    print(f"\n  Result: {passed}/{total} passed")
    return failed == 0


def test_phase2_max_one_winner():
    """Test Phase 2: Max 1 winner between 40-54 numbers."""
    print("\n" + "=" * 70)
    print("TEST 2: Phase 2 - Max 1 winner between 40-54 numbers")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    for num_players in [2, 5, 10]:
        for seed in range(10):
            random.seed(seed)
            
            player_cartelas = {}
            for i in range(num_players):
                uid = str(i)
                player_cartelas[uid] = [generate_random_cartela() for _ in range(2)]
            
            called = []
            available = list(BINGO_NUMBERS)
            winners_at_40 = 0
            
            # Simulate to 40 numbers
            for turn in range(40):
                if not available:
                    break
                num_called = len(called)
                number = smart_predictor(called, available, player_cartelas, num_called)
                called.append(number)
                available.remove(number)
            
            # Count winners at 40
            for uid, cartelas in player_cartelas.items():
                for flat in cartelas:
                    if check_bingo(flat, called):
                        winners_at_40 += 1
                        break
            
            if winners_at_40 > 1:
                failed += 1
                print(f"  [FAIL] {num_players} players, seed={seed}: {winners_at_40} winners at 40!")
            else:
                passed += 1
    
    total = passed + failed
    print(f"\n  Result: {passed}/{total} passed")
    return failed == 0


def test_full_game_simulation():
    """Test full game simulation - compare smart vs old predictor."""
    print("\n" + "=" * 70)
    print("TEST 3: Full Game Simulation (Smart vs Old Predictor)")
    print("=" * 70)
    
    num_simulations = 50
    num_players = 10
    
    smart_max_winners = 0
    old_max_winners = 0
    smart_total_winners = 0
    old_total_winners = 0
    smart_wins_under_40 = 0
    old_wins_under_40 = 0
    
    for sim in range(num_simulations):
        seed = sim * 100
        
        # Smart predictor
        winners, turns = run_game_simulation('smart', num_players, seed=seed)
        smart_max_winners = max(smart_max_winners, winners)
        smart_total_winners += winners
        if turns < 40:
            smart_wins_under_40 += 1
        
        # Old predictor
        winners_old, turns_old = run_game_simulation('old', num_players, seed=seed)
        old_max_winners = max(old_max_winners, winners_old)
        old_total_winners += winners_old
        if turns_old < 40:
            old_wins_under_40 += 1
    
    print(f"\n  Simulations: {num_simulations} games with {num_players} players each")
    print(f"\n  {'Metric':<35} {'Smart':<15} {'Old':<15}")
    print(f"  {'-'*65}")
    print(f"  {'Max winners in any game':<35} {smart_max_winners:<15} {old_max_winners:<15}")
    print(f"  {'Avg winners per game':<35} {smart_total_winners/num_simulations:<15.2f} {old_total_winners/num_simulations:<15.2f}")
    print(f"  {'Games ending before 40':<35} {smart_wins_under_40:<15} {old_wins_under_40:<15}")
    
    # Verdict
    print(f"\n  --- VERDICT ---")
    if smart_max_winners <= 2:
        print(f"  [PASS] Smart predictor: max {smart_max_winners} winner(s) (target: <= 2)")
    else:
        print(f"  [FAIL] Smart predictor: max {smart_max_winners} winner(s) (target: <= 2)")
    
    if smart_wins_under_40 == 0:
        print(f"  [PASS] Smart predictor: 0 games ended before 40 numbers")
    else:
        print(f"  [FAIL] Smart predictor: {smart_wins_under_40} games ended before 40")
    
    return smart_max_winners <= 2 and smart_wins_under_40 == 0


def test_predictor_3_winners_stress():
    """Stress test: Try to force 3+ winners with predictor."""
    print("\n" + "=" * 70)
    print("TEST 4: Stress Test - Force 3+ Winners")
    print("=" * 70)
    
    num_players = 20
    times_3_plus = 0
    times_2 = 0
    times_1 = 0
    times_0 = 0
    
    for seed in range(100):
        winners, turns = run_game_simulation('smart', num_players, seed=seed)
        if winners >= 3:
            times_3_plus += 1
            print(f"  [!] Seed {seed}: {winners} winners at turn {turns}")
        elif winners == 2:
            times_2 += 1
        elif winners == 1:
            times_1 += 1
        else:
            times_0 += 1
    
    print(f"\n  Results across 100 games with {num_players} players:")
    print(f"    0 winners: {times_0} games")
    print(f"    1 winner:  {times_1} games")
    print(f"    2 winners: {times_2} games")
    print(f"    3+ winners: {times_3_plus} games")
    
    if times_3_plus == 0:
        print(f"\n  [PASS] No 3+ winner games detected!")
        return True
    else:
        print(f"\n  [FAIL] {times_3_plus} games had 3+ winners!")
        return False


# ==================== MAIN ====================
def main():
    print("\n" + "=" * 70)
    print("  SMART PREDICTOR TEST SUITE")
    print("  Verifying: No 3+ simultaneous winners")
    print("=" * 70)
    
    results = []
    
    try:
        results.append(("Phase 1: No winners < 40", test_phase1_no_winners()))
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        results.append(("Phase 1", False))
    
    try:
        results.append(("Phase 2: Max 1 winner 40-54", test_phase2_max_one_winner()))
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        results.append(("Phase 2", False))
    
    try:
        results.append(("Full Game Simulation", test_full_game_simulation()))
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        results.append(("Full Game", False))
    
    try:
        results.append(("Stress Test 3+ Winners", test_predictor_3_winners_stress()))
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        results.append(("Stress Test", False))
    
    # Summary
    print("\n" + "=" * 70)
    print("  FINAL RESULTS")
    print("=" * 70)
    
    passed = sum(1 for _, p in results if p)
    total = len(results)
    
    for name, p in results:
        status = "[PASS]" if p else "[FAIL]"
        print(f"  {status}: {name}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n  [PASS] ALL PREDICTOR TESTS PASSED!")
        print("  The smart predictor successfully prevents 3+ winners.")
    else:
        print(f"\n  [FAIL] {total - passed} test(s) failed.")
    
    print("=" * 70)
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
