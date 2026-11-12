(function(){
  // barre de navigation : fond au scroll
  var nav=document.querySelector('.site-nav');
  function onScroll(){ if(nav) nav.classList.toggle('scrolled', window.scrollY>40); }
  onScroll(); window.addEventListener('scroll',onScroll,{passive:true});

  // apparition au scroll
  var els=document.querySelectorAll('.reveal');
  if('IntersectionObserver' in window){
    var io=new IntersectionObserver(function(es){es.forEach(function(e){
      if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}});},{threshold:.12});
    els.forEach(function(el){io.observe(el);});
  } else els.forEach(function(el){el.classList.add('in');});

  // compteurs animés
  document.querySelectorAll('[data-count]').forEach(function(el){
    var target=parseInt(el.dataset.count,10)||0, done=false;
    function run(){ if(done)return; done=true; var t0=null;
      (function step(ts){ t0=t0||ts; var p=Math.min((ts-t0)/1400,1);
        el.textContent=Math.round(target*(1-Math.pow(1-p,3))); if(p<1) requestAnimationFrame(step); })(performance.now()); }
    if('IntersectionObserver' in window){
      new IntersectionObserver(function(es,o){ if(es[0].isIntersecting){run();o.disconnect();} },{threshold:.4}).observe(el);
    } else run();
  });

  // vidéo : si le fichier est absent, on garde le fond dégradé
  document.querySelectorAll('video[data-bg]').forEach(function(v){
    v.addEventListener('error',function(){v.style.display='none';},true);
    var s=v.querySelector('source'); if(s) s.addEventListener('error',function(){v.style.display='none';});
  });

  // carte login / inscription : bascule sans rechargement
  var sw=document.querySelectorAll('button[data-pane],a[data-pane]');
  sw.forEach(function(b){ b.addEventListener('click',function(){ show(b.dataset.pane); }); });
  function show(name){
    document.querySelectorAll('.auth-pane').forEach(function(p){p.classList.toggle('active',p.dataset.name===name);});
    document.querySelectorAll('.auth-switch button').forEach(function(x){x.classList.toggle('active',x.dataset.pane===name);});
    try{history.replaceState(null,'','#'+name);}catch(e){}
  }
  if(document.querySelector('.auth-pane')){
    var initial=(document.body.dataset.pane)||(location.hash==='#signup'?'signup':'login');
    show(initial);
  }
  // afficher / masquer le mot de passe
  document.querySelectorAll('[data-toggle-pass]').forEach(function(b){
    b.addEventListener('click',function(){var i=b.closest('.input-group').querySelector('input');
      i.type=i.type==='password'?'text':'password'; b.querySelector('i').className='bi '+(i.type==='password'?'bi-eye':'bi-eye-slash');});
  });

  // barre de progression + bouton haut de page
  var sp=document.getElementById('sp'), tt=document.getElementById('toTop');
  function prog(){var h=document.documentElement.scrollHeight-innerHeight;
    if(sp) sp.style.width=(h>0?scrollY/h*100:0)+'%'; if(tt) tt.classList.toggle('show',scrollY>600);}
  addEventListener('scroll',prog,{passive:true}); prog();

  // particules dorées du hero
  var pc=document.getElementById('particles');
  if(pc && !matchMedia('(prefers-reduced-motion:reduce)').matches){
    for(var i=0;i<26;i++){var p=document.createElement('i'),sz=4+Math.random()*10;
      p.style.cssText='left:'+Math.random()*100+'%;width:'+sz+'px;height:'+sz+'px;animation-duration:'+(9+Math.random()*12)+'s;animation-delay:'+(-Math.random()*20)+'s';
      pc.appendChild(p);}
  }

  // texte qui s'écrit tout seul
  var rot=document.querySelector('.rotator');
  if(rot){
    var words=rot.dataset.words.split('|'),wi=0,ci=0,del=false;
    if(matchMedia('(prefers-reduced-motion:reduce)').matches){rot.textContent=words[0];}
    else (function tick(){
      var w=words[wi]; rot.textContent=w.slice(0,ci);
      if(!del&&ci<w.length){ci++;setTimeout(tick,95);}
      else if(!del){del=true;setTimeout(tick,1500);}
      else if(ci>0){ci--;setTimeout(tick,50);}
      else{del=false;wi=(wi+1)%words.length;setTimeout(tick,250);}
    })();
  }

  // horloge en direct
  var clk=document.getElementById('liveClock'),dt=document.getElementById('liveDate');
  function tock(){var d=new Date(); if(clk)clk.textContent=d.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
    if(dt)dt.textContent=d.toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long'});}
  tock(); setInterval(tock,15000);
})();
