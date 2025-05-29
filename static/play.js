/* play.js  –  ES-module
   ------------------------------------------------------------------
   * relies on /static/card_stack_system.js  (attaches global CardStack)
   * relies on /static/quiz_logic.js         (exports helper functions)
   * provides: swiping, progress bar, results panel, refresh, play-again,
     share-results-image, and all multiplayer socket handling.
   ------------------------------------------------------------------ */

   // bring the library into the module scope
   import '/static/card_stack_system.js';      // just executes the script
   const CardStack = window.CardStack;         // grab the global handle
   if (!CardStack) console.error('CardStack engine not loaded!');
   import {
     submitAnswer,
     isQuizComplete,
     calculateResults,
     getCompatibility
   } from '/static/quiz_logic.js';
   
   /* ───────────────────────────────────────────────────────────────────
      Session data sent from Flask into window.__PLAY_SESSION__
      ───────────────────────────────────────────────────────────────── */
   const sess          = window.__PLAY_SESSION__ || {};
   const allQuestions  = sess.questions || [];
   const sessionId     = sess.session_id;
   const quizId        = sess.quiz_id || (allQuestions[0] && allQuestions[0].quiz_id) || '';
   const quizTitle     = sess.quiz_title;
   const playerName    = sess.this_player_name || sess.player_name || 'Player';
   let   quizType      = sess.quiz_type || 'thisorthat';     // 'player' / 'competition' / 'thisorthat'
   
   /* auto-detect "player" display mode when options are 'Player 1' / 'Player 2' */
   if (quizType === 'thisorthat' && allQuestions.length) {
     const { option1, option2 } = allQuestions[0];
     if ((option1 === 'Player 1' && option2 === 'Player 2') ||
         (option1 === 'Player 2' && option2 === 'Player 1')) {
       quizType = 'player';
     }
   }
   
   /* ───────────────────────────────────────────────────────────────────
      Local state
      ───────────────────────────────────────────────────────────────── */
   let currentQuestionIndex      = 0;
   let myAnswers                 = [];
   let otherPlayerAnswers        = [];
   let stack                     = null;
   let stackReady                = false;
   let isAnimating               = false;
   
   let newSessionIdForRequester  = null;
   let newSessionIdForInvitee    = null;
   let isInterGamePeriod         = false;   // between games
   const originalGroupId         = sess.shared_session_group || sess.session_id || sessionId || '';
   
   /* local-storage key for progress */
   const LS_KEY = `thisorthat_progress_${sessionId}_${playerName}`;
   
   /* ───────────────────────────────────────────────────────────────────
      DOM helpers
      ───────────────────────────────────────────────────────────────── */
   const $ = sel => document.querySelector(sel);
   
   /* very small toast helper */
   function showNotification(msg, type = 'success', ms = 4000) {
     let wrap = $('#notification-container');
     if (!wrap) {
       wrap = document.createElement('div');
       wrap.id = 'notification-container';
       wrap.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;';
       document.body.appendChild(wrap);
     }
     const n = document.createElement('div');
     n.textContent = msg;
     n.style.cssText = `
       margin-bottom:8px;padding:10px 16px;border-radius:6px;color:#fff;
       background:${{success:'#4caf50',error:'#f44336',info:'#2196f3'}[type]||'#4caf50'};
       box-shadow:0 2px 8px rgba(0,0,0,.2);cursor:pointer;transition:opacity .3s`;
     n.onclick = () => n.remove();
     wrap.appendChild(n);
     setTimeout(()=>{n.style.opacity='0'; setTimeout(()=>n.remove(),300);},ms);
   }
   
   /* copy text fallback */
   function copyToClipboard(text,msg) {
     navigator.clipboard?.writeText(text)
       .then(()=>showNotification(msg||'Copied!'))
       .catch(()=>showNotification('Cannot copy','error'));
   }
   
   /* ───────────────────────────────────────────────────────────────────
      Progress cache
      ───────────────────────────────────────────────────────────────── */
   function saveProgress() {
     try {
       localStorage.setItem(LS_KEY, JSON.stringify({currentQuestionIndex,myAnswers}));
     } catch {}
   }
   function loadProgress() {
     try {
       const parsed = JSON.parse(localStorage.getItem(LS_KEY)||'{}');
       if (Number.isInteger(parsed.currentQuestionIndex) && Array.isArray(parsed.myAnswers)) {
         currentQuestionIndex = parsed.currentQuestionIndex;
         myAnswers = parsed.myAnswers;
         return true;
       }
     } catch {}
     return false;
   }
   /* ───────────────────────────────────────────────────────────────────
      CardStack integration
      ───────────────────────────────────────────────────────────────── */
   function initCardInteractions() {
     if (stackReady) return;
     stack = new CardStack('#card-stack', {
       threshold : 0.25,
       onSwipeLeft  : card => handleSwipe('left',  card),
       onSwipeRight : card => handleSwipe('right', card),
       onCardThrown : ()   => moveToNextQuestion()
     });
     $('#reject-btn').onclick = () => stack.throwCurrentCard('left');
     $('#like-btn').onclick   = () => stack.throwCurrentCard('right');
     stackReady = true;
   }
   
   function handleSwipe(direction/*, cardObj unused now */) {
     if (isAnimating) return;
     isAnimating = true;
   
     const qIdx = currentQuestionIndex;
     const q    = allQuestions[qIdx];
     if (!q) return;
   
     const playerChoice =
         quizType === 'player'
         ? (direction === 'left' ? q.option1 : q.option2)
         : undefined;
   
     submitAnswer(myAnswers, qIdx, direction, playerChoice);
     saveProgress();
     updateProgress();
   }
   
   function moveToNextQuestion() {
     currentQuestionIndex++;
   
     /* update counter */
     $('#current-question').textContent = Math.min(currentQuestionIndex+1,allQuestions.length);
   
     /* quiz finished? */
     if (currentQuestionIndex >= allQuestions.length) {
       socket.emit('player_all_answers',{
         session_id  : sessionId,
         player_name : playerName,
         answers     : myAnswers
       });
       if (isQuizComplete(otherPlayerAnswers, allQuestions.length)) showResults();
       else {            // wait for friend
         $('#card-stack').style.display='none';
         $('#action-buttons-container').style.display='none';
         $('#quiz-complete-container').style.display='block';
       }
       return;
     }
   
     isAnimating = false;
   }
   
   function updateProgress() {
     const pct = (currentQuestionIndex+1)/allQuestions.length*100;
     $('#progress-fill').style.width = `${pct}%`;
   }
   
   /* ───────────────────────────────────────────────────────────────────
      UI mode helpers
      ───────────────────────────────────────────────────────────────── */
   function isSessionCreator() {
     // The creator is the one whose name matches sess.player_name
     return playerName === (sess.player_name || '');
   }
   
   function showWaiting() {
     if (isInterGamePeriod) return;
     // If not the session creator, show loading instead of waiting-for-friend
     if (!isSessionCreator()) {
       $('#waiting-container').style.display   = 'none';
       // Show a loading spinner or message in the results area
       let loadingDiv = document.getElementById('invite-loading');
       if (!loadingDiv) {
         loadingDiv = document.createElement('div');
         loadingDiv.id = 'invite-loading';
         loadingDiv.style = 'text-align:center;padding:3rem;';
         loadingDiv.innerHTML = '<div class="spinner" style="margin-bottom:1.5rem;"></div><div style="font-size:1.2em;">Loading…</div>';
         document.getElementById('game-container').prepend(loadingDiv);
       }
       return;
     } else {
       // Remove loading if present
       const loadingDiv = document.getElementById('invite-loading');
       if (loadingDiv) loadingDiv.remove();
       $('#waiting-container').style.display   = 'block';
     }
     $('#ready-container').style.display     = 'none';
     $('#card-stack').style.display          = 'none';
     $('#action-buttons-container').style.display = 'none';
     $('#quiz-complete-container').style.display  = 'none';
   }
   function showReady(playerNames=[]) {
     if (isInterGamePeriod) return;
     // Remove loading if present
     const loadingDiv = document.getElementById('invite-loading');
     if (loadingDiv) loadingDiv.remove();
     $('#waiting-container').style.display   = 'none';
     $('#ready-container').style.display     = 'block';
     $('#card-stack').style.display          = 'none';
     $('#action-buttons-container').style.display = 'none';
     $('#quiz-complete-container').style.display  = 'none';
     const other = playerNames.find(n=>n!==playerName)||'your friend';
     $('#ready-message').innerHTML = `You and ${other} are connected! Click start when you're ready.`;
   }
   function showQuiz() {
     if (isInterGamePeriod) return;
     $('#waiting-container').style.display   = 'none';
     $('#ready-container').style.display     = 'none';
     $('#card-stack').style.display          = 'block';
     $('#action-buttons-container').style.display = 'flex';
     $('#quiz-complete-container').style.display  = 'none';
     initCardInteractions();
     updateProgress();
   }
   /* expose for inline onclick attributes */
   window.showWaitingInterface = showWaiting;
   window.showReadyInterface   = showReady;
   window.showQuizInterface    = showQuiz;
   
   /* ───────────────────────────────────────────────────────────────────
      Multiplayer  (socket.io 4.x)
      ───────────────────────────────────────────────────────────────── */
   const socket = window.io();
   socket.on('connect', () => {
     socket.emit('join_session_room',{session_id:sessionId,player_name:playerName});
   });
   
   function updateOpponentStatus(names){
     const el=$('#session-status');
     if(!el) return;
     if(names?.length>=2){
       const opp=names.find(n=>n!==playerName);
       el.innerHTML=`<span style="color:#4caf50">${opp} is connected!</span>`;
     }else el.textContent='Waiting for your friend to join...';
   }
   
   socket.on('game_state_updated', data=>{
     updateOpponentStatus(data.player_names);
     if(data.both_ready)          showQuiz();
     else if(data.has_friend)     showReady(data.player_names);
     else                         showWaiting();
   
     if(data.player_names?.length>=2 &&
        isQuizComplete(myAnswers, allQuestions.length) &&
        isQuizComplete(otherPlayerAnswers, allQuestions.length)) {
       showResults();
     }
   });
   
   socket.on('player_all_answers', data=>{
     if(data.player_name!==playerName){
       otherPlayerAnswers=data.answers;
       if(isQuizComplete(myAnswers,allQuestions.length)) showResults();
     }
   });
   
   // Listen for player mapping updates and set window.playerMapping
   socket.on('player_mapping_updated', data => {
     if (data && data.player_mapping) {
       window.playerMapping = data.player_mapping;
       // Always update card stack DOM for player mode, regardless of current text
       if (quizType === 'player') {
         const cards = document.querySelectorAll('.tinder-card');
         cards.forEach(card => {
           const left = card.querySelector('.option-left .option-text');
           const right = card.querySelector('.option-right .option-text');
           // Use the original option1/option2 from the question data for this card
           const idx = parseInt(card.getAttribute('data-question-index'), 10);
           if (!isNaN(idx) && allQuestions[idx]) {
             const q = allQuestions[idx];
             if (left && (q.option1 === 'Player 1' || q.option1 === 'Player 2')) {
               left.textContent = window.playerMapping[q.option1] || q.option1;
             }
             if (right && (q.option2 === 'Player 1' || q.option2 === 'Player 2')) {
               right.textContent = window.playerMapping[q.option2] || q.option2;
             }
           }
         });
       }
     }
   });
   
   /* ───────────────────────────────────────────────────────────────────
      READY button (multiplayer "start")
      ───────────────────────────────────────────────────────────────── */
   window.signalReady = async function signalReady(){
     const btn=$('#start-quiz-btn');
     btn.disabled=true; btn.innerHTML='<i class="fas fa-spinner fa-spin"></i> Starting…';
     try{
       const r=await fetch('/api/player-ready',{
         method:'POST',headers:{'Content-Type':'application/json'},
         body:JSON.stringify({session_id:sessionId,player_name:playerName})
       });
       const j=await r.json();
       if(!j.success) throw new Error(j.error||'Error');
     }catch(e){
       showNotification(e.message,'error');
       btn.disabled=false; btn.innerHTML='<i class="fas fa-play"></i> Start Quiz';
     }
   };
   
   /* ───────────────────────────────────────────────────────────────────
      RESULTS panel
      ───────────────────────────────────────────────────────────────── */
   function getAvatarHtml(name, color) {
     // Generate initials from name
     const initials = name.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();
     return `<span style="display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;border-radius:50%;background:${color};color:#fff;font-weight:bold;font-size:1.1em;box-shadow:0 1px 4px rgba(0,0,0,0.08);margin-bottom:4px;">${initials}</span>`;
   }
   
   function showResults(){
     if(isInterGamePeriod) return;
     $('#waiting-container').style.display='none';
     $('#ready-container').style.display='none';
     $('#card-stack').style.display='none';
     $('#action-buttons-container').style.display='none';
     $('#quiz-complete-container').style.display='block';
   
     const container=$('#completion-results');
     if(!container) return;
   
     const isCompetition =
           quizType==='competition' ||
           (allQuestions[0] && 'correct_answer' in allQuestions[0]);
   
     const results = calculateResults(
           allQuestions,
           myAnswers,
           otherPlayerAnswers,
           isCompetition?'competition':quizType,
           window.playerMapping||{}
     );
   
     let headerHTML='';
     if(isCompetition){
       const {myScore,otherScore}=results;
       let msg='',color='',textColor='#fff';
       const otherPlayer = Object.values(window.playerMapping||{}).find(n=>n!==playerName) || 'Friend';
       if(myScore>otherScore){ msg='🏆 You won!'; color='#4caf50'; textColor='#fff';}
       else if(otherScore>myScore){ msg=`🏆 ${otherPlayer} won!`; color:'#e53935'; textColor:'#fff';}
       else { msg='🤝 It\'s a tie!'; color:'#ffe082'; textColor:'#222';}
       headerHTML = `
         <div style="background:${color};color:${textColor};padding:20px 10px 10px 10px;border-radius:16px 16px 0 0;margin-bottom:0;text-align:center;box-shadow:0 2px 12px rgba(0,0,0,0.08);border:2px solid ${color};">
           <div style="font-size:2.2rem;font-weight:bold;">${msg}</div>
           <div style="font-size:1.2rem;margin-top:0.5em;letter-spacing:1px;">${myScore} <span style='font-size:1.1em;color:${textColor};'>vs</span> ${otherScore}</div>
         </div>`;
     } else {
       const compat = getCompatibility(results.matches, allQuestions.length);
       headerHTML = `
         <div style="background:#42a5f5;color:#fff;padding:20px 10px 10px 10px;border-radius:16px 16px 0 0;margin-bottom:0;text-align:center;box-shadow:0 2px 12px rgba(0,0,0,0.08);border:2px solid #42a5f5;">
           <div style="font-size:2.2rem;font-weight:bold;">${compat}% compatibility</div>
         </div>`;
     }
   
     // Store reactions per question
     if (!window._questionReactions) window._questionReactions = {};
     const reactions = window._questionReactions;
   
     // Helper to render reaction display (for local user, not overlay)
     function renderReactions(idx) {
       const r = reactions[idx] || {};
       if (!r.emoji) return '';
       return `<span class="reaction-display" style="margin-left:8px;font-size:1.3em;vertical-align:middle;">${r.emoji}</span>`;
     }
   
     // Helper to render emoji buttons
     function emojiButtons(idx) {
       return `
         <button class="emoji-btn" data-emoji="clap" data-idx="${idx}" title="Applause" style="background:none;border:none;cursor:pointer;font-size:1.5em;margin:0 0 8px 0;">👏</button>
         <button class="emoji-btn" data-emoji="haha" data-idx="${idx}" title="Haha" style="background:none;border:none;cursor:pointer;font-size:1.5em;margin:0 0 8px 0;">😂</button>
         <button class="emoji-btn" data-emoji="bruh" data-idx="${idx}" title="Bruh" style="background:none;border:none;cursor:pointer;font-size:1.5em;margin:0 0 8px 0;">😑</button>
       `;
     }
   
     // Helper to render share button
     function shareButton(idx) {
       return `<button class="share-question-btn" data-idx="${idx}" title="Share this result" style="background:none;border:none;cursor:pointer;font-size:1.3em;margin-left:8px;"><i class="fas fa-share-alt"></i></button>`;
     }
   
     let items = '';
     const getPlayerColor = (name) => {
       if (name === playerName) return '#2196f3';
       const others = Object.values(window.playerMapping||{}).filter(n=>n!==playerName);
       if (others.length) return '#e53935';
       return '#888';
     };
     const getStatusBadge = (status) => {
       const otherPlayer = Object.values(window.playerMapping||{}).find(n=>n!==playerName) || 'Friend';
       const map = {
         'both_correct': {text:'Both Correct', color:'#4caf50'},
         'my_correct':   {text:`${playerName} Correct`, color:'#2196f3'},
         'other_correct':{text:`${otherPlayer} Correct`, color:'#e53935'},
         'both_wrong':   {text:'Both Wrong', color:'#f44336'},
         'match':        {text:'Match', color:'#4caf50'},
         'mismatch':     {text:'Mismatch', color:'#ffe082', textColor:'#222'},
         'unanswered':   {text:'Unanswered', color:'#9e9e9e'}
       };
       const s = map[status] || {text:status,color:'#bbb'};
       const badgeTextColor = s.textColor || '#fff';
       return `<span style="display:inline-block;background:${s.color};color:${badgeTextColor};padding:2px 10px;border-radius:12px;font-size:0.92em;margin-left:8px;vertical-align:middle;">${s.text}</span>`;
     };
   
     const allPlayers = Object.values(window.playerMapping||{});
     const otherPlayer = allPlayers.find(n=>n!==playerName) || 'Friend';
     const myColor = getPlayerColor(playerName);
     const otherColor = getPlayerColor(otherPlayer);
   
     items = results.comparison.map((r, idx) => {
       const q = r.question;
       const prompt = q.prompt || `${q.option1} or ${q.option2}?`;
       let myAns = r.myDisplayedChoice || '';
       let otherAns = r.otherDisplayedChoice || '';
       // Map Player 1/2 to real names if needed
       if (myAns === 'Player 1' || myAns === 'Player 2') myAns = window.playerMapping && window.playerMapping[myAns] || myAns;
       if (otherAns === 'Player 1' || otherAns === 'Player 2') otherAns = window.playerMapping && window.playerMapping[otherAns] || otherAns;
       return `<div class="result-item status-${r.status}" data-question-idx="${idx}" style="margin-bottom:1.2em;box-shadow:0 2px 10px rgba(66,165,245,0.07);border:2px solid ${getStatusBadge(r.status).match(/background:([^;]+)/)?.[1]||'#bbb'};background:#fff;display:flex;align-items:stretch;position:relative;">
         <div class="emoji-reactions" style="display:flex;flex-direction:column;justify-content:center;align-items:center;padding:0 8px 0 0;min-width:40px;">
           ${emojiButtons(idx)}
           ${renderReactions(idx)}
         </div>
         <div style="flex:1;">
           <div class="prompt" style="font-size:1.08em;font-weight:600;margin-bottom:0.5em;">${prompt} ${getStatusBadge(r.status)}</div>
           <div style="display:flex;gap:1.5em;justify-content:center;align-items:center;margin-top:0.5em;">
             <div style="background:${myColor}10;padding:8px 16px;border-radius:10px;min-width:140px;text-align:center;display:flex;flex-direction:column;align-items:center;border:2px solid ${myColor};">
               ${getAvatarHtml(playerName, myColor)}
               <span style="color:${myColor};font-weight:bold;">${playerName}</span>
               <span style="font-size:1.08em;font-weight:500;margin-top:2px;">${myAns}</span>
             </div>
             <div style="background:${otherColor}10;padding:8px 16px;border-radius:10px;min-width:140px;text-align:center;display:flex;flex-direction:column;align-items:center;border:2px solid ${otherColor};">
               ${getAvatarHtml(otherPlayer, otherColor)}
               <span style="color:${otherColor};font-weight:bold;">${otherPlayer}</span>
               <span style="font-size:1.08em;font-weight:500;margin-top:2px;">${otherAns}</span>
             </div>
           </div>
         </div>
         <div class="share-question" style="display:flex;align-items:center;justify-content:center;padding:0 0 0 8px;min-width:40px;">
           ${shareButton(idx)}
         </div>
       </div>`;
     }).join('');
   
     container.innerHTML = headerHTML + items;
     $('#share-results-btn').style.display='block';
   
     // Add event listeners for emoji buttons
     container.querySelectorAll('.emoji-btn').forEach(btn => {
       btn.onclick = function() {
         const idx = parseInt(this.getAttribute('data-idx'));
         const emojiType = this.getAttribute('data-emoji');
         // Send type and username
         socket.emit('question_reaction', {
           session_id: sessionId,
           question_idx: idx,
           reaction: emojiType,
           from: playerName
         });
       };
     });
   
     // Add event listeners for share buttons
     container.querySelectorAll('.share-question-btn').forEach(btn => {
       btn.onclick = async function() {
         const idx = parseInt(this.getAttribute('data-idx'));
         const resultItem = container.querySelector(`.result-item[data-question-idx='${idx}']`);
         if (!resultItem) return;
         try {
           const canvas = await html2canvas(resultItem, {backgroundColor:'#fff', scale:2});
           const blob = await new Promise(res => canvas.toBlob(res, 'image/png'));
           const fileName = `quiz_result_q${idx+1}_${sessionId.slice(0,4)}.png`;
           if (navigator.canShare && navigator.canShare({ files: [new File([blob],fileName,{type:'image/png'})] })) {
             await navigator.share({
               title : `Quiz result – ${quizTitle} (Q${idx+1})`,
               files : [new File([blob],fileName,{type:'image/png'})]
             });
           } else {
             const a = document.createElement('a');
             a.href = URL.createObjectURL(blob);
             a.download = fileName;
             a.click();
             URL.revokeObjectURL(a.href);
           }
         } catch (e) {
           showNotification('Could not share image','error');
         }
       };
     });
   }
   window.showResults = showResults;
   
   /* ────────────────────────────────────────────────────────────────
      RESULTS REFRESH  ▸ uses /api/multiplayer-results/<sessionId>
      ──────────────────────────────────────────────────────────────── */
   async function refreshResults () {
     const box  = document.querySelector('#completion-results');
     if (!box) return;
   
     box.innerHTML = '<p style="text-align:center">Refreshing…</p>';
     try {
       const r  = await fetch(`/api/multiplayer-results/${sessionId}`);
       const j  = await r.json();
       if (!j.questions || !j.player_answers) throw new Error('Malformed data');
   
       myAnswers        = j.player_answers[playerName]        || [];
       const otherName  = Object.keys(j.player_answers).find(n => n !== playerName);
       otherPlayerAnswers = otherName ? j.player_answers[otherName] : [];
   
       showResults();
       showNotification('Results refreshed','info');
     } catch (e) {
       console.error(e);
       box.innerHTML = '<p style="color:red;text-align:center">Could not refresh 😢</p>';
       showNotification('Refresh failed','error');
     }
   }
   
   /* ────────────────────────────────────────────────────────────────
      PLAY AGAIN  ▸ requests a brand-new session with same quiz
      ──────────────────────────────────────────────────────────────── */
   async function playAnotherQuiz () {
     const btn = document.querySelector('button[data-play-again]') || this;
     btn && (btn.disabled = true);

     // Defensive check
     if (!quizId || !playerName || !originalGroupId) {
       showNotification('Missing quiz or session info. Please reload the page.', 'error');
       btn && (btn.disabled = false);
       return;
     }

     // Debug log
     console.log('Play Another Quiz payload:', {
       quiz_id: quizId,
       player_name: playerName,
       shared_session_group: originalGroupId
     });

     try {
       const r = await fetch('/api/request-new-quiz', {
         method :'POST',
         headers:{'Content-Type':'application/json'},
         body   :JSON.stringify({
           quiz_id            : quizId,
           player_name        : playerName,
           shared_session_group: originalGroupId
         })
       });
       const j = await r.json();
       if (!j.success) throw new Error(j.error);
       // Show waiting modal/UI
       showNotification('Invite sent! Waiting for your friend to accept...', 'info');
       isInterGamePeriod = true;
       const quizComplete = document.getElementById('quiz-complete-container');
       if (quizComplete) {
         quizComplete.innerHTML = '<div style="padding:2rem;text-align:center"><h2>Invite sent!</h2><p>Waiting for your friend to accept the new quiz...</p></div>';
       }
       // Store the new session id for later redirect
       newSessionIdForRequester = j.session_id;
     } catch (e) {
       console.error(e);
       showNotification(e.message,'error');
       btn && (btn.disabled = false);
     }
   }
   
   // Listen for acceptance of the play-again invite
   socket.on('new_game_accepted_and_joined', data => {
     if (data.new_session_id === newSessionIdForRequester) {
       // Redirect to the new session as soon as the friend accepts
       location.href = `/session/${newSessionIdForRequester}?pn=${encodeURIComponent(playerName)}`;
     }
   });

   // Listen for decline or closure of the play-again invite
   socket.on('play_again_declined', data => {
     if (data.declined_session_id === newSessionIdForRequester) {
       isInterGamePeriod = false;
       // Update the results panel to show the decline message
       const quizComplete = document.getElementById('quiz-complete-container');
       if (quizComplete) {
         quizComplete.innerHTML = `
           <div style="padding:2rem;text-align:center">
             <h2>Invite sent!</h2>
             <p style="color:#f44336;font-weight:bold;margin-top:1.5rem;">Your friend declined the new quiz invitation.</p>
           </div>
         `;
       }
       showNotification('Your friend declined the new quiz invitation.', 'error');
       // Do NOT redirect to home, keep on results page
     }
   });
   socket.on('play_again_invite_closed', data => {
     if (data.closed_session_id_for_invitee === newSessionIdForRequester) {
       isInterGamePeriod = false;
       showNotification('Quiz invitation was closed.', 'info');
       window.refreshResults && window.refreshResults();
     }
   });
   
   // Listen for play again invite (for the friend)
   socket.on('play_again_invite', data => {
     // Only show if you are NOT the requester
     if (data.requester_name !== playerName) {
       showPlayAgainInviteModal(data);
     }
   });

   function showPlayAgainInviteModal(data) {
     const modal = document.getElementById('playAgainInviteModal');
     if (!modal) return;
     document.getElementById('playAgainInviteText').textContent =
       `${data.requester_name} wants to play "${data.quiz_title}". Play again?`;
     modal.style.display = 'flex';

     // Accept
     document.getElementById('acceptPlayAgainBtn').onclick = async function() {
       modal.style.display = 'none';
       // Send accept to backend
       await fetch('/api/accept-quiz-request', {
         method: 'POST',
         headers: {'Content-Type': 'application/json'},
         body: JSON.stringify({
           new_session_id: data.new_session_id_to_join,
           player_name: playerName,
           shared_session_group: originalGroupId
         })
       });
       // Redirect to new session
       location.href = `/session/${data.new_session_id_to_join}?pn=${encodeURIComponent(playerName)}`;
     };

     // Decline
     document.getElementById('declinePlayAgainBtn').onclick = async function() {
       modal.style.display = 'none';
       // Disable Play Another Quiz button for the friend
       const playAgainBtn = document.querySelector('button[data-play-again]');
       if (playAgainBtn) playAgainBtn.disabled = true;
       await fetch('/api/decline-play-again', {
         method: 'POST',
         headers: {'Content-Type': 'application/json'},
         body: JSON.stringify({
           declined_session_id: data.new_session_id_to_join,
           original_session_group: originalGroupId
         })
       });
       showNotification('You declined the play again invite.', 'info');
     };
   }
   
   /* ────────────────────────────────────────────────────────────────
      SHARE RESULTS IMAGE  ▸ html2canvas + Web-Share fallback
      ──────────────────────────────────────────────────────────────── */
   async function shareResultsImage () {
     const node = document.querySelector('#completion-results');
     if (!node) return;
   
     const btn  = document.querySelector('#share-results-btn');
     btn && (btn.disabled = true);
   
     try {
       const canvas   = await html2canvas(node,{backgroundColor:'#fff',scale:2});
       const blob     = await new Promise(res => canvas.toBlob(res,'image/png'));
       const fileName = `quiz_results_${sessionId.slice(0,4)}.png`;
   
       if (navigator.canShare && navigator.canShare({ files: [new File([blob],fileName,{type:'image/png'})] })) {
         await navigator.share({
           title : `Quiz results – ${quizTitle}`,
           files : [new File([blob],fileName,{type:'image/png'})]
         });
       } else {
         /* fallback – download */
         const a = document.createElement('a');
         a.href = URL.createObjectURL(blob);
         a.download = fileName;
         a.click();
         URL.revokeObjectURL(a.href);
       }
     } catch (e) {
       console.error(e);
       showNotification('Could not create image','error');
     } finally {
       btn && (btn.disabled = false);
     }
   }
   
   /* ────────────────────────────────────────────────────────────────
      expose to inline-HTML handlers
      ──────────────────────────────────────────────────────────────── */
   window.refreshResults     = refreshResults;
   window.playAnotherQuiz    = playAnotherQuiz;
   window.shareResultsImage  = shareResultsImage;
   
   /* ───────────────────────────────────────────────────────────────────
      FIRST LOAD: restore progress & initialise correct UI
      ───────────────────────────────────────────────────────────────── */
   if(loadProgress()){
     /* update UI counter/prompt */
     $('#current-question').textContent = currentQuestionIndex+1;
     updateProgress();
   }
   
   /* ask server where we stand (will immediately trigger our handlers) */
   socket.emit('request_game_state',{session_id:sessionId});
   
   // --- At the very end of the file, outside any block ---
   function toggleSessionInfo() {
     const det = document.getElementById('session-details');
     const ico = document.getElementById('toggle-icon');
     if (!det || !ico) return;
     const open = det.style.display !== 'none';
     det.style.display = open ? 'none' : 'block';
     ico.classList.toggle('fa-chevron-down', open);
     ico.classList.toggle('fa-chevron-up', !open);
   }
   
   function shareSession() {
     const url = `${location.origin}/join/${sessionId}`;
     const text = `🎮 Join me for "${quizTitle}" quiz!`;
     if (navigator.share) {
       navigator.share({ title: quizTitle, text, url })
         .catch(() => copyToClipboard(url, 'Link copied!'));
     } else copyToClipboard(url, 'Link copied!');
   }
   
   window.toggleSessionInfo = toggleSessionInfo;
   window.shareSession      = shareSession;
   
   // Listen for question reaction events from the other player
   socket.on('question_reaction', data => {
     // data: {question_idx, reaction, from}
     const idx = data && typeof data.question_idx === 'number' ? data.question_idx : null;
     const reaction = data && data.reaction;
     const from = data && data.from || '';
     if (idx === null || !reaction) return;

     // Find the result item
     const resultItem = document.querySelector(`.result-item[data-question-idx='${idx}']`);
     if (!resultItem) return;

     // Determine overlay message and emoji
     let msg = '';
     let emoji = '';
     if (reaction === 'clap') {
       emoji = '👏';
       msg = `${from || 'Your friend'} applauds your answer.`;
     } else if (reaction === 'haha') {
       emoji = '😂';
       msg = `${from || 'Your friend'} laughs at this.`;
     } else if (reaction === 'bruh') {
       emoji = '😑';
       msg = `${from || 'Your friend'} is like bruuuuuuuuuuuuuuh...`;
     }

     // Create overlay
     const overlay = document.createElement('div');
     overlay.className = 'reaction-overlay';
     overlay.style.position = 'absolute';
     overlay.style.top = 0;
     overlay.style.left = 0;
     overlay.style.width = '100%';
     overlay.style.height = '100%';
     overlay.style.display = 'flex';
     overlay.style.alignItems = 'center';
     overlay.style.justifyContent = 'center';
     overlay.style.background = 'rgba(255,255,255,0.7)';
     overlay.style.zIndex = 10;
     overlay.style.fontSize = '2em';
     overlay.style.fontWeight = 'bold';
     overlay.style.color = '#222';
     overlay.innerHTML = `<span style="margin-right:0.5em;">${emoji}</span> <span>${msg}</span>`;
     resultItem.appendChild(overlay);
     setTimeout(() => {
       overlay.style.transition = 'opacity 0.7s';
       overlay.style.opacity = 0;
       setTimeout(() => overlay.remove(), 700);
     }, 1200);
   });
   