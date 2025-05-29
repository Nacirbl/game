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
        }));
        
        // Reverse order so the first card is on top
        this.cards.reverse();
        this.currentCardIndex = 0;
    }
    
    attachEventListeners() {
        // Mouse events
        this.container.addEventListener('mousedown', this.handleStart.bind(this));
        document.addEventListener('mousemove', this.handleMove.bind(this));
        document.addEventListener('mouseup', this.handleEnd.bind(this));
        
        // Touch events
        this.container.addEventListener('touchstart', this.handleStart.bind(this), { passive: false });
        document.addEventListener('touchmove', this.handleMove.bind(this), { passive: false });
        document.addEventListener('touchend', this.handleEnd.bind(this));
        
        // Prevent context menu on long press
        this.container.addEventListener('contextmenu', (e) => e.preventDefault());
    }
    
    handleStart(e) {
        if (this.currentCardIndex >= this.cards.length) return;
        
        const currentCard = this.cards[this.currentCardIndex];
        if (!currentCard) return;
        
        // Check if the event target is the current card or its child
        if (!currentCard.element.contains(e.target)) return;
        
        e.preventDefault();
        
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
        
        // Add active class for better visual feedback
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
        
        // Calculate rotation based on horizontal movement
        const rotation = Math.max(-this.options.maxRotation, 
            Math.min(this.options.maxRotation, deltaX * this.options.rotationMultiplier));
        
        // Update card transform
        currentCard.transform = {
            x: deltaX,
            y: deltaY * 0.3, // Reduce vertical movement
            rotation
        };
        
        this.applyTransform(currentCard);
        this.updateOverlays(currentCard, deltaX);
    }
    
    handleEnd(e) {
        if (!this.isDragging || this.currentCardIndex >= this.cards.length) return;
        
        const currentCard = this.cards[this.currentCardIndex];
        if (!currentCard || !currentCard.isDragging) return;
        
        e.preventDefault();
        
        this.isDragging = false;
        currentCard.isDragging = false;
        currentCard.element.style.cursor = 'grab';
        currentCard.element.classList.remove('dragging');
        
        const deltaX = this.currentX - this.startX;
        const absDeltaX = Math.abs(deltaX);
        
        if (absDeltaX > this.options.throwThreshold) {
            // Throw the card
            this.throwCard(currentCard, deltaX > 0 ? 'right' : 'left');
        } else {
            // Snap back
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
        
        // Trigger callbacks
        if (direction === 'left' && this.options.onSwipeLeft) {
            this.options.onSwipeLeft(card);
        } else if (direction === 'right' && this.options.onSwipeRight) {
            this.options.onSwipeRight(card);
        }
        
        if (this.options.onCardThrown) {
            this.options.onCardThrown(card, direction);
        }
        
        // Remove card after animation
        setTimeout(() => {
            card.element.remove();
            this.nextCard();
        }, this.options.throwOutDuration);
        
        // Hide overlays
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
            if (index < this.currentCardIndex) return; // Skip removed cards
            
            const relativeIndex = index - this.currentCardIndex;
            const scale = 1 - (relativeIndex * this.options.scaleStep);
            const translateY = relativeIndex * this.options.stackOffset;
            const zIndex = this.cards.length - relativeIndex;
            
            if (relativeIndex === 0) {
                // Current card
                card.element.style.cursor = 'grab';
                card.element.style.pointerEvents = 'auto';
            } else {
                // Background cards
                card.element.style.cursor = 'default';
                card.element.style.pointerEvents = 'none';
            }
            
            card.element.style.zIndex = zIndex;
            
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
        
        if (deltaX > 0) {
            // Swiping right
            rightOverlay.style.opacity = opacity;
            leftOverlay.style.opacity = 0;
        } else if (deltaX < 0) {
            // Swiping left
            leftOverlay.style.opacity = opacity;
            rightOverlay.style.opacity = 0;
        } else {
            leftOverlay.style.opacity = 0;
            rightOverlay.style.opacity = 0;
        }
    }
    
    hideOverlays(card) {
        const leftOverlay = card.element.querySelector('.choice-overlay.left');
        const rightOverlay = card.element.querySelector('.choice-overlay.right');
        
        if (leftOverlay) leftOverlay.style.opacity = 0;
        if (rightOverlay) rightOverlay.style.opacity = 0;
    }
    
    // Public method to programmatically throw cards
    throwCurrentCard(direction) {
        if (this.currentCardIndex >= this.cards.length) return false;
        
        const currentCard = this.cards[this.currentCardIndex];
        if (!currentCard) return false;
        
        this.throwCard(currentCard, direction);
        return true;
    }
    
    // Get current card info
    getCurrentCard() {
        if (this.currentCardIndex >= this.cards.length) return null;
        return this.cards[this.currentCardIndex];
    }
    
    // Check if there are more cards
    hasMoreCards() {
        return this.currentCardIndex < this.cards.length;
    }
    
    // Get progress
    getProgress() {
        return {
            current: this.currentCardIndex,
            total: this.cards.length,
            percentage: (this.currentCardIndex / this.cards.length) * 100
        };
    }
}

// Enhanced CSS for smooth animations
const cardStackStyles = `
    .card-stack {
        position: relative;
        width: 350px;
        height: 500px;
        margin: 0 auto;
        perspective: 1000px;
        touch-action: none; /* Prevent scrolling while swiping */
    }
    
    .tinder-card {
        position: absolute;
        width: 100%;
        height: 100%;
        border-radius: var(--border-radius, 15px);
        background: white;
        box-shadow: 0 8px 40px rgba(0,0,0,0.12);
        cursor: grab;
        user-select: none;
        transform-origin: center center;
        overflow: hidden;
        will-change: transform, opacity;
        backface-visibility: hidden;
        -webkit-backface-visibility: hidden;
        display: flex;
        flex-direction: column;
        transition: transform 0.2s ease-out;
    }
    
    .tinder-card.dragging {
        z-index: 1000 !important;
        box-shadow: 0 15px 50px rgba(0,0,0,0.2);
    }
    
    .choice-overlay {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 4rem;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 0.2rem;
        opacity: 0;
        transition: opacity 0.1s ease;
        pointer-events: none;
        text-shadow: 0 2px 10px rgba(0,0,0,0.3);
        border-radius: var(--border-radius, 15px);
    }
    
    .choice-overlay.left {
        background: linear-gradient(45deg, rgba(255,68,88,0.1), rgba(255,68,88,0.3));
        color: #ff4458;
        border: 4px solid #ff4458;
    }
    
    .choice-overlay.right {
        background: linear-gradient(45deg, rgba(66,165,245,0.1), rgba(66,165,245,0.3));
        color: #42a5f5;
        border: 4px solid #42a5f5;
    }
    
    .action-btn {
        width: 70px;
        height: 70px;
        border-radius: 50%;
        border: none;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.8rem;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        position: relative;
        overflow: hidden;
        background: linear-gradient(45deg, transparent, rgba(255,255,255,0.1));
    }
    
    .action-btn:hover {
        transform: scale(1.1);
        box-shadow: 0 8px 30px rgba(0,0,0,0.25);
    }
    
    .action-btn:active {
        transform: scale(0.95);
    }
    
    .action-btn.reject {
        background: linear-gradient(45deg, #667eea, #764ba2);
        color: white;
    }
    
    .action-btn.like {
        background: linear-gradient(45deg, #f093fb, #f5576c);
        color: white;
    }
    
    /* Add ripple effect */
    .action-btn::before {
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        width: 0;
        height: 0;
        border-radius: 50%;
        background: rgba(255,255,255,0.3);
        transform: translate(-50%, -50%);
        transition: width 0.3s, height 0.3s;
    }
    
    .action-btn:active::before {
        width: 100px;
        height: 100px;
    }
    
    @media (max-width: 768px) {
        .card-stack {
            width: 90vw;
            max-width: 350px;
            height: 70vh;
            max-height: 500px;
        }
        
        .action-btn {
            width: 60px;
            height: 60px;
            font-size: 1.5rem;
        }
        
        .choice-overlay {
            font-size: 3rem;
        }
    }
    
    @media (max-width: 480px) {
        .card-stack {
            width: 95vw;
            height: 65vh;
        }
        
        .action-btn {
            width: 55px;
            height: 55px;
            font-size: 1.3rem;
        }
        
        .choice-overlay {
            font-size: 2.5rem;
        }
    }
`;

// Inject styles
if (!document.getElementById('card-stack-styles')) {
    const styleSheet = document.createElement('style');
    styleSheet.id = 'card-stack-styles';
    styleSheet.textContent = cardStackStyles;
    document.head.appendChild(styleSheet);
}

// Export for use in your application
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CardStack;
} else {
    window.CardStack = CardStack;
}