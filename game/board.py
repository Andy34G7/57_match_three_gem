import math
import random
import pygame

GRID_SIZE = 8
HINT_DELAY_MS = 5000
TILE_SIZE = 60
GEM_COLORS = [
    (220, 50, 50),   # Red
    (50, 200, 50),   # Green
    (50, 100, 240),  # Blue
    (240, 200, 40),  # Yellow
    (180, 50, 220),  # Purple
    (240, 130, 40),  # Orange
]


class Gem:
   
    def __init__(self, color, target_row, col):
        self.color = color
        self.target_row = target_row
        self.col = col
        self.current_y = (target_row - 2) * TILE_SIZE
        self.target_y = target_row * TILE_SIZE
        self.fall_speed = 12.0
        self.special = None  # None, 'row' or 'col' (4-in-a-row line-clear gem)

    def update(self):
        if self.current_y < self.target_y:
            self.current_y += self.fall_speed
            if self.current_y > self.target_y:
                self.current_y = self.target_y

    def is_animating(self):
        return self.current_y < self.target_y


class Board:

    def __init__(self, offset_x, offset_y, target_score=500, max_moves=20):
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.target_score = target_score
        self.max_moves = max_moves
        self.grid = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.selected = None
        self.score = 0
        self.moves_remaining = max_moves
        self.last_input = pygame.time.get_ticks()
        self.hint = None
        self.reset()

    def reset(self):
        self.score = 0
        self.moves_remaining = self.max_moves
        self.selected = None
        self.touch()
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                color = random.choice(GEM_COLORS)
                gem = Gem(color, r, c)
                gem.current_y = gem.target_y  
                self.grid[r][c] = gem

        self.resolve_matches(make_specials=False)

    def is_animating(self):
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if self.grid[r][c] and self.grid[r][c].is_animating():
                    return True
        return False

    def swap_gems(self, pos1, pos2):
        r1, c1 = pos1
        r2, c2 = pos2

        g1, g2 = self.grid[r1][c1], self.grid[r2][c2]
        self.grid[r1][c1], self.grid[r2][c2] = g2, g1

        if self.grid[r1][c1]:
            self.grid[r1][c1].target_row = r1
            self.grid[r1][c1].target_y = r1 * TILE_SIZE
            self.grid[r1][c1].current_y = r1 * TILE_SIZE

        if self.grid[r2][c2]:
            self.grid[r2][c2].target_row = r2
            self.grid[r2][c2].target_y = r2 * TILE_SIZE
            self.grid[r2][c2].current_y = r2 * TILE_SIZE

    def is_adjacent(self, pos1, pos2):
        r1, c1 = pos1
        r2, c2 = pos2
        return abs(r1 - r2) + abs(c1 - c2) == 1

    def touch(self):
        """Register player activity: restarts the idle timer and hides the hint."""
        self.last_input = pygame.time.get_ticks()
        self.hint = None

    def scan_runs(self):
        """Return all straight runs of 3+ same-colour gems as (cells, orientation)."""
        runs = []
        for r in range(GRID_SIZE):
            c = 0
            while c < GRID_SIZE:
                g = self.grid[r][c]
                end = c + 1
                while g and end < GRID_SIZE and self.grid[r][end] and self.grid[r][end].color == g.color:
                    end += 1
                if g and end - c >= 3:
                    runs.append(([(r, k) for k in range(c, end)], "row"))
                c = end
        for c in range(GRID_SIZE):
            r = 0
            while r < GRID_SIZE:
                g = self.grid[r][c]
                end = r + 1
                while g and end < GRID_SIZE and self.grid[end][c] and self.grid[end][c].color == g.color:
                    end += 1
                if g and end - r >= 3:
                    runs.append(([(k, c) for k in range(r, end)], "col"))
                r = end
        return runs

    def find_matches(self):
        matched = set()
        for cells, _ in self.scan_runs():
            matched.update(cells)
        return matched

    def find_hint(self):
        """Find an adjacent swap that would create a match, or None."""
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                for dr, dc in ((0, 1), (1, 0)):
                    r2, c2 = r + dr, c + dc
                    if r2 >= GRID_SIZE or c2 >= GRID_SIZE:
                        continue
                    self.swap_gems((r, c), (r2, c2))
                    found = bool(self.find_matches())
                    self.swap_gems((r, c), (r2, c2))
                    if found:
                        return (r, c), (r2, c2)
        return None

    def drop_and_refill(self):
        for c in range(GRID_SIZE):
            empty_slots = 0
            for r in range(GRID_SIZE - 1, -1, -1):
                if self.grid[r][c] is None:
                    empty_slots += 1
                elif empty_slots > 0:
                    gem = self.grid[r][c]
                    gem.target_row = r + empty_slots
                    gem.target_y = (r + empty_slots) * TILE_SIZE
                    self.grid[r + empty_slots][c] = gem
                    self.grid[r][c] = None

            for r in range(empty_slots):
                color = random.choice(GEM_COLORS)
                gem = Gem(color, r, c)
                gem.current_y = -((empty_slots - r) * TILE_SIZE)
                self.grid[r][c] = gem

    def expand_specials(self, cells):
        """Special gems in the cleared set detonate their whole row/column (chains)."""
        cells = set(cells)
        queue = list(cells)
        while queue:
            r, c = queue.pop()
            gem = self.grid[r][c]
            if gem and gem.special:
                line = (
                    [(r, k) for k in range(GRID_SIZE)]
                    if gem.special == "row"
                    else [(k, c) for k in range(GRID_SIZE)]
                )
                for cell in line:
                    if cell not in cells:
                        cells.add(cell)
                        queue.append(cell)
        return cells

    def resolve_matches(self, preferred=(), make_specials=True):
        """Clear matches until stable. Returns points earned (cascade multiplied)."""
        points = 0
        cascade = 0
        while True:
            runs = self.scan_runs()
            if not runs:
                break
            cascade += 1
            matched = set()
            spawns = {}
            for cells, orient in runs:
                matched.update(cells)
                if make_specials and len(cells) >= 4:
                    spot = next((p for p in preferred if p in cells), cells[len(cells) // 2])
                    spawns[spot] = orient
            to_clear = self.expand_specials(matched)
            for spot in spawns:
                to_clear.discard(spot)
            points += len(to_clear) * 10 * cascade  # combo multiplier x1, x2, x3...
            for r, c in to_clear:
                self.grid[r][c] = None
            for (r, c), orient in spawns.items():
                self.grid[r][c].special = orient
            preferred = ()
            self.drop_and_refill()
        return points

    def process_swap(self, pos1, pos2):
        if not self.is_adjacent(pos1, pos2) or self.is_game_over() or self.is_animating():
            return False

        self.swap_gems(pos1, pos2)
        matches = self.find_matches()

        if not matches:
            self.swap_gems(pos1, pos2)  # invalid swap: revert, no move spent
            return False

        self.moves_remaining -= 1
        self.score += self.resolve_matches(preferred=(pos1, pos2))
        return True

    def is_game_over(self):
        return self.score >= self.target_score or self.moves_remaining <= 0

    def check_result(self):
        if self.score >= self.target_score:
            return "WIN"
        if self.moves_remaining <= 0:
            return "LOSS"
        return None

    def update(self):
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if self.grid[r][c]:
                    self.grid[r][c].update()

        idle = pygame.time.get_ticks() - self.last_input
        if idle > HINT_DELAY_MS and self.hint is None and not self.is_game_over() and not self.is_animating():
            self.hint = self.find_hint()

    def render(self, surface):
        board_rect = pygame.Rect(
            self.offset_x, self.offset_y, GRID_SIZE * TILE_SIZE, GRID_SIZE * TILE_SIZE
        )
        pygame.draw.rect(surface, (20, 22, 28), board_rect, border_radius=8)
        pygame.draw.rect(surface, (60, 65, 75), board_rect, width=3, border_radius=8)

        now = pygame.time.get_ticks()
        pulse = (math.sin(now / 150.0) + 1) / 2  # 0..1

        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                gem = self.grid[r][c]
                if gem:
                    x = self.offset_x + c * TILE_SIZE
                    y = self.offset_y + gem.current_y
                    tile_rect = pygame.Rect(x + 2, y + 2, TILE_SIZE - 4, TILE_SIZE - 4)

                    pygame.draw.rect(surface, gem.color, tile_rect, border_radius=10)
                    pygame.draw.rect(
                        surface, (255, 255, 255), tile_rect, width=1, border_radius=10
                    )
                    if gem.special:
                        glow = int(120 + 135 * pulse)
                        pygame.draw.rect(
                            surface, (255, 255, glow), tile_rect, width=4, border_radius=10
                        )
                        cx, cy = tile_rect.center
                        if gem.special == "row":
                            pygame.draw.line(surface, (255, 255, 255), (x + 10, cy), (x + TILE_SIZE - 10, cy), 5)
                        else:
                            pygame.draw.line(surface, (255, 255, 255), (cx, y + 10), (cx, y + TILE_SIZE - 10), 5)

                if self.hint and (r, c) in self.hint:
                    hx = self.offset_x + c * TILE_SIZE
                    hy = self.offset_y + r * TILE_SIZE
                    hint_rect = pygame.Rect(hx + 2, hy + 2, TILE_SIZE - 4, TILE_SIZE - 4)
                    overlay = pygame.Surface(hint_rect.size, pygame.SRCALPHA)
                    pygame.draw.rect(
                        overlay, (255, 255, 255, int(40 + 110 * pulse)),
                        overlay.get_rect(), border_radius=10,
                    )
                    surface.blit(overlay, hint_rect.topleft)
                    pygame.draw.rect(
                        surface, (255, 240, 120), hint_rect.inflate(int(6 * pulse), int(6 * pulse)),
                        width=3, border_radius=10,
                    )

                if self.selected == (r, c):
                    sel_x = self.offset_x + c * TILE_SIZE
                    sel_y = self.offset_y + r * TILE_SIZE
                    sel_rect = pygame.Rect(sel_x + 2, sel_y + 2, TILE_SIZE - 4, TILE_SIZE - 4)
                    pygame.draw.rect(
                        surface, (255, 255, 255), sel_rect, width=4, border_radius=10
                    )
