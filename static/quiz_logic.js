// quiz_logic.js
// All quiz play logic for all quiz types: thisorthat, competition, player
// This file is meant to be imported by play.html or other client code

/**
 * Collects an answer for a player for a given question index.
 * @param {Array} answersArray - Array of answer objects for the player.
 * @param {number} questionIndex - Index of the question being answered.
 * @param {string} choice - 'left' or 'right'.
 * @param {string} [playerChoice] - For player mode, the chosen player's name.
 */
export function submitAnswer(answersArray, questionIndex, choice, playerChoice = undefined) {
    // Ensure the answers array is long enough to store this answer
    while (answersArray.length <= questionIndex) {
        answersArray.push(null);
    }
    // Store the answer
    answersArray[questionIndex] = {
        choice: choice,
        playerChoice: playerChoice
    };
    console.log(`Answer submitted for question ${questionIndex}:`, answersArray[questionIndex]);
}

/**
 * Checks if a player has completed the quiz.
 * @param {Array} answersArray - Array of answer objects for the player.
 * @param {number} totalQuestions - Total number of questions in the quiz.
 * @returns {boolean}
 */
export function isQuizComplete(answersArray, totalQuestions) {
    // Check if the answers array has an answer for every question
    if (answersArray.length < totalQuestions) {
        return false;
    }
    for (let i = 0; i < totalQuestions; i++) {
        if (!answersArray[i] || !answersArray[i].choice) {
            return false;
        }
    }
    return true;
}

/**
 * Calculates results for all quiz types.
 * @param {Array} questions - Array of quiz questions.
 * @param {Array} myAnswers - Array of answer objects for the current player.
 * @param {Array} otherPlayerAnswers - Array of answer objects for the other player.
 * @param {string} quizType - 'thisorthat', 'competition', or 'player'.
 * @param {Object} playerMapping - Mapping of player names to their actual names.
 * @returns {Object} - { matches, myScore, otherScore, comparison: [per-question result] }
 */
export function calculateResults(questions, myAnswers, otherPlayerAnswers, quizType, playerMapping = {}) {
    let matches = 0;
    let myScore = 0;
    let otherScore = 0;
    const comparison = [];
    console.log('Calculating results with inputs:', { questions, myAnswers, otherPlayerAnswers, quizType, playerMapping });

    for (let i = 0; i < questions.length; i++) {
        const question = questions[i];
        const myAnswer = myAnswers[i];
        const otherAnswer = otherPlayerAnswers[i];

        if (!myAnswer || !otherAnswer) {
            comparison.push({
                question: question,
                status: 'unanswered',
                myDisplayedChoice: '',
                otherDisplayedChoice: ''
            });
            continue;
        }

        const myChoice = myAnswer.choice;
        const otherChoice = otherAnswer.choice;
        let myDisplayedChoice = myChoice === 'left' ? question.option1 : question.option2;
        let otherDisplayedChoice = otherChoice === 'left' ? question.option1 : question.option2;

        if (myAnswer.playerChoice) {
            myDisplayedChoice = myAnswer.playerChoice;
        } else if (playerMapping && (myDisplayedChoice === 'Player 1' || myDisplayedChoice === 'Player 2')) {
            myDisplayedChoice = playerMapping[myDisplayedChoice] || myDisplayedChoice;
        }

        if (otherAnswer.playerChoice) {
            otherDisplayedChoice = otherAnswer.playerChoice;
        } else if (playerMapping && (otherDisplayedChoice === 'Player 1' || otherDisplayedChoice === 'Player 2')) {
            otherDisplayedChoice = playerMapping[otherDisplayedChoice] || otherDisplayedChoice;
        }

        if (quizType === 'competition') {
            const correctAnswer = question.correct_answer;
            const myCorrect = (myChoice === 'left' && correctAnswer === 'option1') || (myChoice === 'right' && correctAnswer === 'option2');
            const otherCorrect = (otherChoice === 'left' && correctAnswer === 'option1') || (otherChoice === 'right' && correctAnswer === 'option2');

            if (myCorrect) myScore++;
            if (otherCorrect) otherScore++;

            let status = '';
            if (myCorrect && otherCorrect) status = 'both_correct';
            else if (myCorrect) status = 'my_correct';
            else if (otherCorrect) status = 'other_correct';
            else status = 'both_wrong';

            comparison.push({
                question: question,
                status: status,
                myDisplayedChoice: myDisplayedChoice,
                otherDisplayedChoice: otherDisplayedChoice
            });
        } else {
            const isMatch = myChoice === otherChoice;
            if (isMatch) matches++;
            comparison.push({
                question: question,
                status: isMatch ? 'match' : 'mismatch',
                myDisplayedChoice: myDisplayedChoice,
                otherDisplayedChoice: otherDisplayedChoice
            });
        }
    }

    console.log('Results calculated:', { matches, myScore, otherScore, comparison });
    return {
        matches: matches,
        myScore: myScore,
        otherScore: otherScore,
        comparison: comparison
    };
}

/**
 * Utility to get the compatibility percentage for 'thisorthat' or 'player' mode.
 * @param {number} matches
 * @param {number} total
 * @returns {number}
 */
export function getCompatibility(matches, total) {
    if (total === 0) return 0;
    return Math.round((matches / total) * 100);
} 