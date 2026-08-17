// Card Stack System - swipeable tinder-style card deck
//
// Built on Pointer Events (unified mouse/touch/pen) so behavior is identical
// across devices. Mobile-friendly by design:
//   - relative throw threshold (fraction of card width, not fixed px)
//   - flick detection via smoothed velocity (fast short swipes commit)
//   - pointer capture (finger sliding off-screen or second fingers can't
//     corrupt the drag)
//   - touch-action: none on the stack (CSS) stops page scroll during drags
//     without the old body-overflow hack
//   - rAF-coalesced transform updates for 120Hz touch screens
//   - tap left/right half of the card to answer
//   - restoreTo() so a swipe can be undone (cards are hidden, not destroyed)

class CardStack {
    constructor(containerSelector, options = {}) {
        this.container = document.querySelector(containerSelector);
        if (!this.container) {
            throw new Error(`Container ${containerSelector} not found`);
        }

        this.options = {
            throwThresholdRatio: 0.30, // commit when dragged past 30% of card width
            minThrowThreshold: 50,     // ...but never less than 50px (small cards)
            flickVelocity: 0.55,       // px/ms - a flick faster than this commits
            flickMinDistance: 0.4,     // flicks must still travel 40% of threshold
            tapMaxDistance: 10,        // px - release within this = tap
            tapMaxDuration: 350,       // ms
            rotationMultiplier: 0.05,
            snapBackDuration: 300,
            snapBackEasing: 'cubic-bezier(0.175, 0.885, 0.32, 1.28)', // slight spring
            throwOutDuration: 300,
            maxRotation: 15,
            stackOffset: 8,
            scaleStep: 0.04,
            maxStackDepth: 3,
            onSwipeLeft: null,
            onSwipeRight: null,
            onCardThrown: null,
            onTapLeft: null,           // optional; defaults to a left throw
            onTapRight: null,
            ...options
        };

        this.cards = [];
        this.currentCardIndex = 0;
        this.dragging = null;       // active drag state or null
        this.rafPending = false;
        this.resizeTimer = null;
        this._log = [];             // capped mutation log (debugging)

        this.init();
    }

    _trace(what) {
        this._log.push(`${what} -> idx ${this.currentCardIndex}`);
        if (this._log.length > 60) this._log.shift();
    }

    init() {
        this.setupCards();
        this.attachEventListeners();
        this.updateCardPositions();
    }

    setupCards() {
        // Cards are expected in natural question order (cards[0] = first
        // question). game.js appends them that way; index === array position
        // === question index, which skipTo/restoreTo/throw guards rely on.
        const cardElements = this.container.querySelectorAll('.tinder-card');
        this.cards = Array.from(cardElements).map((element, index) => ({
            element,
            index,
            isDragging: false,
            thrown: false,
            transform: { x: 0, y: 0, rotation: 0 }
        }));
        this.currentCardIndex = 0;
    }

    attachEventListeners() {
        this.container.addEventListener('pointerdown', this.handleStart.bind(this));

        // Move/end on window filtered by pointerId: robust even if the
        // pointer leaves the card, the window, or hits a popup
        window.addEventListener('pointermove', this.handleMove.bind(this), { passive: false });
        window.addEventListener('pointerup', this.handleEnd.bind(this), { passive: false });
        window.addEventListener('pointercancel', this.handleCancel.bind(this), { passive: false });

        this.container.addEventListener('contextmenu', e => e.preventDefault());

        // Keep the visual stack consistent across rotation / resize
        const onResize = () => {
            clearTimeout(this.resizeTimer);
            this.resizeTimer = setTimeout(() => this.updateCardPositions(), 150);
        };
        window.addEventListener('resize', onResize);
        window.addEventListener('orientationchange', onResize);
    }

    /* ── Thresholds ──────────────────────────────────────────── */

    getThrowThreshold() {
        const card = this.cards[this.currentCardIndex];
        const width = (card && card.element.offsetWidth) || this.container.offsetWidth || 320;
        return Math.max(this.options.minThrowThreshold, width * this.options.throwThresholdRatio);
    }

    /* ── Drag lifecycle ──────────────────────────────────────── */

    handleStart(e) {
        if (e.pointerType === 'mouse' && e.button !== 0) return;
        if (this.currentCardIndex >= this.cards.length) return;
        // Stale-drag guard: if a previous gesture's pointerup was swallowed,
        // clear it after a beat instead of blocking input forever
        if (this.dragging && performance.now() - this.dragging.startTime > 3000) {
            const stale = this.dragging.card;
            this.dragging = null;
            if (stale) {
                stale.isDragging = false;
                stale.element.classList.remove('dragging');
                this.snapBack(stale);
            }
        }
        if (this.dragging) return; // one drag at a time (multi-touch guard)

        const card = this.cards[this.currentCardIndex];
        if (!card || card.thrown || !card.element.contains(e.target)) return;

        e.preventDefault();

        // Capture so all further events for this finger come to the card,
        // even if it leaves the element or the window
        try { card.element.setPointerCapture(e.pointerId); } catch {}

        card.isDragging = true;
        card.element.classList.add('dragging');
        card.element.style.willChange = 'transform';

        this.dragging = {
            card,
            pointerId: e.pointerId,
            startX: e.clientX,
            startY: e.clientY,
            curX: e.clientX,
            curY: e.clientY,
            startTime: performance.now(),
            lastX: e.clientX,
            lastT: performance.now(),
            vx: 0
        };
    }

    handleMove(e) {
        if (!this.dragging || e.pointerId !== this.dragging.pointerId) return;
        e.preventDefault();

        const now = performance.now();
        const dt = now - this.dragging.lastT;
        if (dt > 0) {
            const instVx = (e.clientX - this.dragging.lastX) / dt;
            // Exponential smoothing: recent motion dominates
            this.dragging.vx = 0.6 * this.dragging.vx + 0.4 * instVx;
            this.dragging.lastX = e.clientX;
            this.dragging.lastT = now;
        }
        this.dragging.curX = e.clientX;
        this.dragging.curY = e.clientY;

        // Coalesce to one style write per frame (120Hz screens)
        if (!this.rafPending) {
            this.rafPending = true;
            requestAnimationFrame(() => {
                this.rafPending = false;
                this.applyDrag();
            });
        }
    }

    applyDrag() {
        if (!this.dragging) return;
        const { card, startX, startY, curX, curY } = this.dragging;
        if (!card || !card.element) return;

        const deltaX = curX - startX;
        const deltaY = curY - startY;

        const rotation = Math.round(Math.max(
            -this.options.maxRotation,
            Math.min(this.options.maxRotation, deltaX * this.options.rotationMultiplier)
        ) * 10) / 10;

        card.transform = { x: Math.round(deltaX), y: Math.round(deltaY * 0.3), rotation };
        this.applyTransform(card);
        this.updateOverlays(card, deltaX);
    }

    handleEnd(e) {
        if (!this.dragging || e.pointerId !== this.dragging.pointerId) return;
        e.preventDefault();

        const drag = this.dragging;
        this.dragging = null;

        const card = drag.card;
        card.isDragging = false;
        card.element.classList.remove('dragging');
        card.element.style.willChange = 'auto';

        const deltaX = drag.curX - drag.startX;
        const deltaY = drag.curY - drag.startY;
        const duration = performance.now() - drag.startTime;
        const threshold = this.getThrowThreshold();
        const absX = Math.abs(deltaX);

        const isTap = absX < this.options.tapMaxDistance &&
                      Math.abs(deltaY) < this.options.tapMaxDistance &&
                      duration < this.options.tapMaxDuration;

        if (isTap) {
            // Tap-to-answer: left half = left option, right half = right
            const rect = card.element.getBoundingClientRect();
            const side = (drag.curX - rect.left) < rect.width / 2 ? 'left' : 'right';
            const tapHandler = side === 'left' ? this.options.onTapLeft : this.options.onTapRight;
            if (tapHandler) {
                tapHandler(card);
            } else {
                this.throwCard(card, side, 0.8);
            }
            return;
        }

        const pastThreshold = absX > threshold;
        const isFlick = Math.abs(drag.vx) > this.options.flickVelocity &&
                        absX > threshold * this.options.flickMinDistance;

        if (pastThreshold || isFlick) {
            const direction = (deltaX !== 0 ? deltaX : drag.vx) > 0 ? 'right' : 'left';
            this.throwCard(card, direction, drag.vx);
        } else {
            this.snapBack(card);
        }
    }

    handleCancel(e) {
        if (!this.dragging || e.pointerId !== this.dragging.pointerId) return;
        const card = this.dragging.card;
        this.dragging = null;
        if (card) {
            card.isDragging = false;
            card.element.classList.remove('dragging');
            card.element.style.willChange = 'auto';
            this.snapBack(card);
        }
    }

    /* ── Commit / cancel ─────────────────────────────────────── */

    throwCard(card, direction, velocity = 0) {
        if (!card || card.thrown) return;
        card.thrown = true;
        card.flying = true;   // throw animation in progress - syncTo must not touch it
        this._trace(`throwCard(card${card.index},${direction}) [idx ${this.currentCardIndex}]`);

        // Faster flicks fly out quicker, with a touch more spin
        const speed = Math.min(1.6, Math.max(0.7, Math.abs(velocity) / 0.8));
        const duration = Math.round(this.options.throwOutDuration / speed);
        const rotation = (direction === 'right' ? 30 : -30) * (0.6 + 0.4 * speed);

        const throwDistance = window.innerWidth + card.element.offsetWidth;
        const throwX = direction === 'right' ? throwDistance : -throwDistance;
        const throwY = card.transform.y - 80;

        card.element.style.transition =
            `transform ${duration}ms cubic-bezier(0.25, 0.46, 0.45, 0.94), opacity ${duration}ms ease`;
        card.element.style.transform =
            `translateX(${throwX}px) translateY(${throwY}px) rotate(${rotation}deg)`;
        card.element.style.opacity = '0';

        if (direction === 'left' && this.options.onSwipeLeft) this.options.onSwipeLeft(card);
        if (direction === 'right' && this.options.onSwipeRight) this.options.onSwipeRight(card);
        if (this.options.onCardThrown) this.options.onCardThrown(card, direction);

        setTimeout(() => {
            card.flying = false;
            // Hide rather than remove so undo (restoreTo) can bring it back
            card.element.style.display = 'none';
            // Only advance if nothing already moved the stack past this card
            // (e.g. syncTo() ran during the throw animation)
            if (this.currentCardIndex === card.index) {
                this.nextCard();
                this._trace(`timeout-next(card${card.index})`);
            }
        }, duration);

        this.hideOverlays(card);
    }

    snapBack(card) {
        card.element.style.transition =
            `transform ${this.options.snapBackDuration}ms ${this.options.snapBackEasing}`;
        card.transform = { x: 0, y: 0, rotation: 0 };
        this.applyTransform(card);
        this.hideOverlays(card);

        setTimeout(() => {
            card.element.style.transition = '';
        }, this.options.snapBackDuration);
    }

    nextCard() {
        this.currentCardIndex++;
        this.updateCardPositions();
    }

    /* ── Positioning ─────────────────────────────────────────── */

    updateCardPositions() {
        this.cards.forEach((card, index) => {
            if (index < this.currentCardIndex || card.thrown) return;

            const relativeIndex = index - this.currentCardIndex;
            const depth = Math.min(relativeIndex, this.options.maxStackDepth);
            const scale = 1 - (depth * this.options.scaleStep);
            const translateY = depth * this.options.stackOffset;
            const zIndex = this.cards.length - relativeIndex;

            card.element.style.display = '';
            card.element.style.zIndex = zIndex;
            card.element.style.cursor = relativeIndex === 0 ? 'grab' : 'default';
            card.element.style.pointerEvents = relativeIndex === 0 ? 'auto' : 'none';
            // Cards deeper than the visible stack stay hidden behind
            card.element.style.visibility = relativeIndex > this.options.maxStackDepth ? 'hidden' : 'visible';

            if (!card.isDragging) {
                card.element.style.transition = '';
                card.element.style.opacity = relativeIndex > this.options.maxStackDepth ? '0' : '1';
                card.element.style.transform = `translateY(${translateY}px) scale(${scale})`;
            }
        });
    }

    applyTransform(card) {
        const { x, y, rotation } = card.transform;
        card.element.style.transform = `translate(${x}px, ${y}px) rotate(${rotation}deg)`;
    }

    updateOverlays(card, deltaX) {
        const leftOverlay = card.element.querySelector('.choice-overlay.left');
        const rightOverlay = card.element.querySelector('.choice-overlay.right');
        if (!leftOverlay || !rightOverlay) return;

        const threshold = this.getThrowThreshold();
        const absX = Math.abs(deltaX);
        const opacity = Math.min(absX / threshold, 1) * 0.8;

        leftOverlay.style.opacity = deltaX < 0 ? opacity : 0;
        rightOverlay.style.opacity = deltaX > 0 ? opacity : 0;
    }

    hideOverlays(card) {
        const leftOverlay = card.element.querySelector('.choice-overlay.left');
        const rightOverlay = card.element.querySelector('.choice-overlay.right');
        if (leftOverlay) leftOverlay.style.opacity = 0;
        if (rightOverlay) rightOverlay.style.opacity = 0;
    }

    /* ── Public API ──────────────────────────────────────────── */

    throwCurrentCard(direction) {
        if (this.currentCardIndex >= this.cards.length) return false;
        const currentCard = this.cards[this.currentCardIndex];
        if (!currentCard || currentCard.thrown) return false;
        this.throwCard(currentCard, direction, 0.9);
        return true;
    }

    // Jump the stack forward without animations - used to resync the
    // visual stack with restored progress after a page refresh
    skipTo(index) {
        if (index <= this.currentCardIndex) return;
        this.syncTo(index);
    }

    // Idempotent force-align: whatever state the cards are in, make the
    // stack show exactly `index` as the top card. Called by the renderer on
    // every state update so the visual stack can never drift from the truth.
    syncTo(index) {
        index = Math.max(0, Math.min(index, this.cards.length));
        this.cards.forEach((card, i) => {
            if (card.flying) return;   // mid-throw: let the animation finish
            const gone = i < index;
            if (gone !== card.thrown) card.thrown = gone;
            if (gone) {
                card.element.style.display = 'none';
            } else {
                card.element.style.display = '';
                card.element.style.opacity = '1';
                card.element.style.transition = '';
                card.transform = { x: 0, y: 0, rotation: 0 };
            }
        });
        this.currentCardIndex = index;
        this.updateCardPositions();
        this._trace(`syncTo(${index})`);
    }
    // Bring back a previously thrown card (undo). Returns the restored index
    // or null when there is nothing before the current card to restore.
    restoreTo(index) {
        if (index < 0 || index >= this.cards.length) return null;
        if (index >= this.currentCardIndex) return null;
        this.syncTo(index);
        return index;
    }

    getCurrentCard() {
        return this.currentCardIndex < this.cards.length ? this.cards[this.currentCardIndex] : null;
    }

    hasMoreCards() {
        return this.currentCardIndex < this.cards.length;
    }

    getProgress() {
        return {
            current: this.currentCardIndex,
            total: this.cards.length,
            percentage: (this.currentCardIndex / this.cards.length) * 100
        };
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = CardStack;
} else {
    window.CardStack = window.CardStack || CardStack;
}
