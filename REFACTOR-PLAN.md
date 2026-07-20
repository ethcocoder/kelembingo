# Kelem Bingo - UI Clone & Refactor Plan

## Overview
Split the monolithic `game.html` (653 lines) into modular HTML files, restructure JS connections, and implement a cloned UI design inspired by two reference bingo apps (Yehulu Bingo & Beteseb Bingo).

---

## Phase 1: Split game.html into Multiple HTML Files

### Current State
- Single `game.html` contains 5 screens, 6 modals, overlays, and all inline HTML
- 13 JS files already exist and are well-organized
- Navigation uses `navigateTo(screen)` with CSS class toggling

### New File Structure

```
dashboard/
├── game.html                    (Shell - loads all pages dynamically)
├── css/
│   ├── game.css                (Existing - enhanced)
│   └── components.css          (NEW - component-specific styles)
├── js/
│   ├── firebase.js             (Existing)
│   ├── constants.js            (Existing)
│   ├── state.js                (Existing)
│   ├── audio.js                (Existing)
│   ├── helpers.js              (Existing)
│   ├── auth.js                 (Existing)
│   ├── ui.js                   (Existing - enhanced with page loader)
│   ├── card-select.js          (Existing)
│   ├── game-board.js           (Existing)
│   ├── history.js              (Existing)
│   ├── wallet.js               (Existing)
│   ├── rules.js                (Existing)
│   ├── main.js                 (Existing)
│   └── page-loader.js          (NEW - dynamic page loading system)
├── pages/
│   ├── home.html               (Home screen content)
│   ├── game-board.html         (Game board screen content)
│   ├── history.html            (History screen content)
│   ├── wallet.html             (Wallet screen content)
│   └── profile.html            (Profile screen content)
└── components/
    ├── header.html             (Telegram header component)
    ├── bottom-nav.html         (Bottom navigation bar)
    ├── win-modal.html          (Win celebration modal)
    ├── rules-modal.html        (Rules modal)
    ├── transfer-modal.html     (Transfer funds modal)
    ├── withdraw-modal.html     (Withdraw modal)
    ├── register-modal.html     (Registration modal)
    ├── card-select.html        (Card selection overlay)
    ├── loading-overlay.html    (Loading overlay)
    └── toast.html              (Toast notification)
```

### Shell Game.html (New Structure)
```html
<!-- game.html becomes a minimal shell -->
<body class="bg-bingo-dark">
    <div id="telegram-header"></div>
    <div id="app-container">
        <!-- Pages loaded dynamically here -->
        <div id="screen-home" class="screen active"></div>
        <div id="screen-game" class="screen"></div>
        <div id="screen-history" class="screen"></div>
        <div id="screen-wallet" class="screen"></div>
        <div id="screen-profile" class="screen"></div>
    </div>
    <div id="bottom-nav"></div>
    <!-- Modals loaded here -->
    <div id="modals-container"></div>
    <div id="loading-overlay"></div>
    <div id="toast"></div>
    
    <!-- Scripts -->
    <script src="js/firebase.js"></script>
    <script src="js/constants.js"></script>
    <script src="js/state.js"></script>
    <script src="js/audio.js"></script>
    <script src="js/helpers.js"></script>
    <script src="js/auth.js"></script>
    <script src="js/ui.js"></script>
    <script src="js/card-select.js"></script>
    <script src="js/game-board.js"></script>
    <script src="js/history.js"></script>
    <script src="js/wallet.js"></script>
    <script src="js/rules.js"></script>
    <script src="js/page-loader.js"></script>
    <script src="js/main.js"></script>
</body>
```

### page-loader.js (NEW)
- `loadPage(screenName)` - Fetches HTML from `/pages/{name}.html`, injects into screen div
- `loadComponent(targetId, componentPath)` - Loads component HTML into target element
- `loadAllComponents()` - Loads header, bottom-nav, modals on startup
- Caches loaded pages in memory to avoid re-fetching
- Triggers custom event `pageLoaded` after injection for JS re-initialization

---

## Phase 2: UI Clone Design Implementation

### Design Analysis from Reference Images

#### Image 1 - Yehulu Bingo (Primary Reference)
- **Layout**: Split view - Master grid (left) + Game info (right)
- **Master Grid**: 5 columns (B/I/N/G/O) × 15 rows, small cells with number text
- **Called Numbers**: Horizontal tag strip at top-right with colored pills
- **Number Announcement**: Large circular element with golden conic-gradient ring
- **Cartela**: 5×5 card below announcement, orange header bar
- **Stats Bar**: Horizontal row with Game ID, Players, Bet, Derash, Called
- **Bottom Bar**: Leave (red), Refresh, Auto toggle, AUTOMATIC button
- **Colors**: Deep navy background, blue/purple/green/orange accent colors

#### Image 2 - Beteseb Bingo (Secondary Reference)
- **Layout**: Full-width number grid + Cartela below
- **Number Grid**: 8-column grid with orange numbered tiles (1-96)
- **Called Numbers**: Green highlight on called numbers
- **Cartela**: Below grid, 5×5 with B-I-N-G-O headers
- **Stats**: Main Wallet, Play Wallet, Stake, Timer pill
- **Navigation**: Bottom tab bar (Game, History, Wallet, Profile)
- **Header**: App name with Back + Refresh buttons

### UI Enhancements to Implement

#### 1. Enhanced Game Board Layout
```
┌─────────────────────────────────────────┐
│ ← Close    Yehulu Bingo    ⋮ Menu      │
├─────────────────────────────────────────┤
│ GAME ID │ PLAYERS │ BET │ DERASH │ CALLED│
├─────────────────────────────────────────┤
│ ┌──────────┐  ┌─────────────────────┐   │
│ │ B I N G O│  │ B-2  I-18  O-74    │   │
│ │ ┌─┬─┬─┬─┐│  │ ┌─────────────┐    │   │
│ │ │1│16│31│46││ │ │   B-2      │    │   │
│ │ ├─┼─┼─┼─┤│  │ │  (circle)   │    │   │
│ │ │2│17│32│47││ │ └─────────────┘    │   │
│ │ ├─┼─┼─┼─┤│  │                     │   │
│ │ │...│  │  │  │ CARTELA NO: 22     │   │
│ │ └─┴─┴─┴─┘│  │ ┌─┬─┬─┬─┬─┐        │   │
│ └──────────┘  │ │B│I│N│G│O│        │   │
│               │ ├─┼─┼─┼─┼─┤        │   │
│               │ │ │ │ │ │ │        │   │
│               │ └─┴─┴─┴─┴─┘        │   │
│               └─────────────────────┘   │
├─────────────────────────────────────────┤
│ ✕ LEAVE  ↻ REFRESH  Auto [●] AUTOMATIC│
└─────────────────────────────────────────┘
```

#### 2. Visual Enhancements
- **Master Grid Cells**: Colored backgrounds per letter (B=blue, I=purple, N=pink, G=green, O=orange)
- **Called Numbers**: Glowing border animation on master grid
- **Number Circle**: Larger, with animated conic-gradient border and pulse effect
- **Cartela Cards**: Rounded corners, colored headers, marked cells with green gradient
- **Stats Bar**: Glass-morphism cards with colored borders
- **Bottom Navigation**: Icon + label, active state with orange highlight
- **Card Selection Grid**: 8-column layout with orange numbered tiles (matching Image 2)

#### 3. Color Scheme Updates
```css
/* Primary Colors */
--bg-primary: #0D1117;        /* Deep navy */
--bg-secondary: #1A1A2E;      /* Dark card */
--bg-accent: #111326;         /* Slightly lighter navy */

/* BINGO Letter Colors */
--color-b: #3B82F6;           /* Blue */
--color-i: #8B5CF6;           /* Purple */
--color-n: #D946EF;           /* Pink/Magenta */
--color-g: #10B981;           /* Green */
--color-o: #F97316;           /* Orange */

/* Accent Colors */
--accent-orange: #FF8C00;     /* Primary accent */
--accent-green: #10B981;      /* Success/Win */
--accent-gold: #FFD700;       /* Number circle ring */
```

---

## Phase 3: Implementation Steps

### Step 1: Create Directory Structure
```bash
mkdir -p dashboard/pages dashboard/components
```

### Step 2: Extract HTML into Separate Files

#### Pages to Extract:
1. **pages/home.html** (lines 52-121 of game.html)
   - Brand bar, welcome card, Play Now CTA, live stats, balance, how-to-play
   
2. **pages/game-board.html** (lines 124-275)
   - Header bar, game stats, countdown, master grid, called tags, number circle, cartelas, bottom bar
   
3. **pages/history.html** (lines 278-294)
   - History list with empty state and loading shimmer
   
4. **pages/wallet.html** (lines 297-329)
   - Balance display, deposit/withdraw buttons, transfer, transactions
   
5. **pages/profile.html** (lines 332-376)
   - Avatar, stats, earnings, settings, help, logout

#### Components to Extract:
1. **components/header.html** (lines 41-49)
   - Telegram header with close, title, menu buttons

2. **components/bottom-nav.html** (lines 379-398)
   - 4-tab navigation (Game, History, Wallet, Profile)

3. **components/win-modal.html** (lines 401-429)
   - Celebration modal with confetti, crown, winner info

4. **components/rules-modal.html** (lines 432-452)
   - How to Play modal

5. **components/transfer-modal.html** (lines 455-481)
   - Fund transfer modal

6. **components/withdraw-modal.html** (lines 484-518)
   - Withdrawal modal

7. **components/register-modal.html** (lines 521-541)
   - Registration modal

8. **components/card-select.html** (lines 544-620)
   - Card selection overlay

9. **components/loading-overlay.html** (lines 623-630)
   - Loading spinner

10. **components/toast.html** (lines 633-637)
    - Toast notification

### Step 3: Create page-loader.js
```javascript
// Page loader system
const PageLoader = {
    cache: {},
    
    async loadPage(screenName) {
        if (this.cache[screenName]) {
            document.getElementById(`screen-${screenName}`).innerHTML = this.cache[screenName];
            return;
        }
        const response = await fetch(`pages/${screenName}.html`);
        const html = await response.text();
        this.cache[screenName] = html;
        document.getElementById(`screen-${screenName}`).innerHTML = html;
        document.dispatchEvent(new CustomEvent('pageLoaded', { detail: screenName }));
    },
    
    async loadComponent(targetId, path) {
        const response = await fetch(`components/${path}`);
        const html = await response.text();
        document.getElementById(targetId).innerHTML = html;
    },
    
    async init() {
        await Promise.all([
            this.loadComponent('telegram-header', 'header.html'),
            this.loadComponent('bottom-nav', 'bottom-nav.html'),
        ]);
        // Load modals container
        const modalPaths = ['win-modal', 'rules-modal', 'transfer-modal', 'withdraw-modal', 'register-modal', 'card-select', 'loading-overlay', 'toast'];
        // Load all modals...
    }
};
```

### Step 4: Update ui.js Navigation
```javascript
// Enhanced navigateTo with page loading
function navigateTo(screen) {
    // ... existing logic ...
    // Ensure page is loaded
    PageLoader.loadPage(screen).then(() => {
        // Re-initialize any screen-specific JS
    });
}
```

### Step 5: Update main.js Initialization
```javascript
document.addEventListener('DOMContentLoaded', async function() {
    restoreAudioSettings();
    // Load all components first
    await PageLoader.init();
    // Then initialize user
    initUser();
});
```

### Step 6: Implement Visual Enhancements

#### A. Enhanced Master Grid Styling
```css
.master-cell {
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    transition: all 0.25s ease;
}
.master-cell.col-b { background: rgba(59,130,246,0.2); color: rgba(59,130,246,0.7); }
.master-cell.col-i { background: rgba(139,92,246,0.2); color: rgba(139,92,246,0.7); }
.master-cell.col-n { background: rgba(217,70,239,0.2); color: rgba(217,70,239,0.7); }
.master-cell.col-g { background: rgba(16,185,129,0.2); color: rgba(16,185,129,0.7); }
.master-cell.col-o { background: rgba(249,115,22,0.2); color: rgba(249,115,22,0.7); }
```

#### B. Enhanced Number Circle
```css
.number-circle-outer {
    width: 100px;
    height: 100px;
    background: conic-gradient(
        from 0deg,
        #FFD700,
        #FF8C00,
        #FFD700,
        #FF8C00,
        #FFD700
    );
    animation: circle-spin 3s linear infinite, circle-pulse 1.5s ease-in-out infinite;
}
@keyframes circle-spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
```

#### C. Card Selection Grid (Image 2 Style)
```css
.card-select-grid {
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 6px;
}
.card-num {
    background: linear-gradient(135deg, #FF8C00, #FF6B00);
    color: white;
    border-radius: 8px;
    aspect-ratio: 1;
    font-weight: 800;
    box-shadow: 0 2px 8px rgba(255,140,0,0.3);
}
.card-num.selected {
    background: linear-gradient(135deg, #10B981, #059669);
    box-shadow: 0 0 16px rgba(16,185,129,0.5);
}
```

#### D. Enhanced Cartela Styling
```css
.cartela-header {
    background: linear-gradient(135deg, #FF8C00, #FF6B00);
    padding: 6px;
    border-radius: 8px 8px 0 0;
    font-weight: 800;
    letter-spacing: 1px;
}
.cartela-cell {
    background: rgba(30,35,64,0.8);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 4px;
    padding: 8px 4px;
    text-align: center;
    font-weight: 700;
    transition: all 0.2s ease;
}
.cartela-cell.marked {
    background: linear-gradient(135deg, #10B981, #059669);
    box-shadow: 0 0 12px rgba(16,185,129,0.4);
}
```

### Step 7: Update game-board.js for New Layout
- Modify `buildMasterGrid()` to add letter-specific color classes
- Enhance `showNumberAnnouncement()` for larger circle
- Update `buildCartelaGrid()` for improved cell styling
- Add smooth transitions for number highlighting

### Step 8: Update card-select.js for Image 2 Style
- Modify card grid rendering to use orange tile style
- Update preview area styling
- Enhance timer pill design

---

## Phase 4: Testing Checklist

- [ ] All pages load correctly via page-loader
- [ ] Navigation between screens works
- [ ] Game board renders master grid with colors
- [ ] Number announcement circle displays correctly
- [ ] Cartela grids render with new styling
- [ ] Card selection grid shows orange tiles
- [ ] Modals open/close properly
- [ ] Real-time updates still work (WebSocket)
- [ ] Audio playback functions
- [ ] Auto-mark toggle works
- [ ] Bingo detection still works
- [ ] Win celebration modal displays
- [ ] Mobile responsiveness maintained
- [ ] Telegram Mini App integration intact

---

## Implementation Order

1. **Create directory structure** (pages/, components/)
2. **Create page-loader.js** (dynamic loading system)
3. **Extract all HTML** into separate files
4. **Update game.html** to shell structure
5. **Update main.js** to use page-loader
6. **Update ui.js** navigation to work with loaded pages
7. **Implement visual enhancements** in CSS
8. **Update game-board.js** for new grid styling
9. **Update card-select.js** for Image 2 style
10. **Test complete flow** end-to-end
