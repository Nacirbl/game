// Professional Card Stack System
// Replaces Swing.js with custom implementation for better performance and control

class CardStack {
    constructor(containerSelector, options = {}) {
        this.container = document.querySelector(containerSelector);
        if (!this.container) {
            throw new Error(`Container ${containerSelector} not found`);
        }

        this.options = {
            throwThreshold: 120,
            rotationMultiplier: 0.05,
            snapBackDuration: 300,
            throwOutDuration: 300,
            maxRotation: 15,
            stackOffset: 3,
            scaleStep: 0.02,
            onSwipeLeft: null,
            onSwipeRight: null,
            onCardThrown: null,
            ...options
        };

        this.cards = [];
        this.currentCardIndex = 0;
        this.isDragging = false;
        this.startX = 0;
        this.startY = 0;
        this.currentX = 0;
        this.currentY = 0;

        this.init();
    }

    init() {
        this.setupCards();
        this.attachEventListeners();
        this.updateCardPositions();
    }

    setupCards() {
        const cardElements = this.container.querySelectorAll('.tinder-card');
        this.cards = Array.from(cardElements).map((element, index) => ({
            element,
            index,
            isActive: index === 0,
            isDragging: false,
            transform: { x: 0, y: 0, rotation: 0 }
        })).reverse();
        this.currentCardIndex = 0;
    }

    attachEventListeners() {
        this.container.addEventListener('mousedown', this.handleStart.bind(this));
        document.addEventListener('mousemove', this.handleMove.bind(this));
        document.addEventListener('mouseup', this.handleEnd.bind(this));

        this.container.addEventListener('touchstart', this.handleStart.bind(this), { passive: false });
        document.addEventListener('touchmove', this.handleMove.bind(this), { passive: false });
        document.addEventListener('touchend', this.handleEnd.bind(this));

        this.container.addEventListener('contextmenu', e => e.preventDefault());
    }

    handleStart(e) {
        if (this.currentCardIndex >= this.cards.length) return;
        const currentCard = this.cards[this.currentCardIndex];
        if (!currentCard || !currentCard.element.contains(e.target)) return;

        e.preventDefault();
        document.body.style.overflow = 'hidden';

        const clientX = e.clientX || e.touches[0].clientX;
        const clientY = e.clientY || e.touches[0].clientY;

        this.startX = clientX;
        this.startY = clientY;
        this.currentX = clientX;
        this.currentY = clientY;
        this.isDragging = true;

        currentCard.isDragging = true;
        currentCard.element.style.cursor = 'grabbing';
        currentCard.element.style.transition = 'none';
        currentCard.element.classList.add('dragging');
    }

    handleMove(e) {
        if (!this.isDragging || this.currentCardIndex >= this.cards.length) return;

        e.preventDefault();
        const currentCard = this.cards[this.currentCardIndex];
        if (!currentCard || !currentCard.isDragging) return;

        const clientX = e.clientX || e.touches[0].clientX;
        const clientY = e.clientY || e.touches[0].clientY;

        const deltaX = clientX - this.startX;
        const deltaY = clientY - this.startY;

        this.currentX = clientX;
        this.currentY = clientY;

        const rotation = Math.max(-this.options.maxRotation, Math.min(this.options.maxRotation, deltaX * this.options.rotationMultiplier));
        currentCard.transform = { x: deltaX, y: deltaY * 0.3, rotation };

        this.applyTransform(currentCard);
        this.updateOverlays(currentCard, deltaX);
    }

    handleEnd(e) {
        if (!this.isDragging || this.currentCardIndex >= this.cards.length) return;

        const currentCard = this.cards[this.currentCardIndex];
        if (!currentCard || !currentCard.isDragging) return;

        e.preventDefault();
        document.body.style.overflow = '';

        this.isDragging = false;
        currentCard.isDragging = false;
        currentCard.element.style.cursor = 'grab';
        currentCard.element.classList.remove('dragging');

        const deltaX = this.currentX - this.startX;
        const absDeltaX = Math.abs(deltaX);

        if (absDeltaX > this.options.throwThreshold) {
            this.throwCard(currentCard, deltaX > 0 ? 'right' : 'left');
        } else {
            this.snapBack(currentCard);
        }
    }

    throwCard(card, direction) {
        const throwDistance = window.innerWidth + card.element.offsetWidth;
        const throwX = direction === 'right' ? throwDistance : -throwDistance;
        const rotation = direction === 'right' ? 30 : -30;

        card.element.style.transition = `transform ${this.options.throwOutDuration}ms cubic-bezier(0.25, 0.46, 0.45, 0.94)`;
        card.element.style.transform = `translateX(${throwX}px) translateY(-100px) rotate(${rotation}deg)`;
        card.element.style.opacity = '0';

        if (direction === 'left' && this.options.onSwipeLeft) this.options.onSwipeLeft(card);
        if (direction === 'right' && this.options.onSwipeRight) this.options.onSwipeRight(card);
        if (this.options.onCardThrown) this.options.onCardThrown(card, direction);

        setTimeout(() => {
            card.element.remove();
            this.nextCard();
        }, this.options.throwOutDuration);

        this.hideOverlays(card);
    }

    snapBack(card) {
        card.element.style.transition = `transform ${this.options.snapBackDuration}ms cubic-bezier(0.25, 0.46, 0.45, 0.94)`;
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

    updateCardPositions() {
        this.cards.forEach((card, index) => {
            if (index < this.currentCardIndex) return;

            const relativeIndex = index - this.currentCardIndex;
            const scale = 1 - (relativeIndex * this.options.scaleStep);
            const translateY = relativeIndex * this.options.stackOffset;
            const zIndex = this.cards.length - relativeIndex;

            card.element.style.zIndex = zIndex;
            card.element.style.cursor = relativeIndex === 0 ? 'grab' : 'default';
            card.element.style.pointerEvents = relativeIndex === 0 ? 'auto' : 'none';

            if (!card.isDragging) {
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

        const absX = Math.abs(deltaX);
        const maxOpacity = 0.8;
        const opacity = Math.min(absX / this.options.throwThreshold, 1) * maxOpacity;

        leftOverlay.style.opacity = deltaX < 0 ? opacity : 0;
        rightOverlay.style.opacity = deltaX > 0 ? opacity : 0;
    }

    hideOverlays(card) {
        const leftOverlay = card.element.querySelector('.choice-overlay.left');
        const rightOverlay = card.element.querySelector('.choice-overlay.right');
        if (leftOverlay) leftOverlay.style.opacity = 0;
        if (rightOverlay) rightOverlay.style.opacity = 0;
    }

    throwCurrentCard(direction) {
        if (this.currentCardIndex >= this.cards.length) return false;
        const currentCard = this.cards[this.currentCardIndex];
        if (!currentCard) return false;
        this.throwCard(currentCard, direction);
        return true;
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
    window.CardStack = CardStack;
}
