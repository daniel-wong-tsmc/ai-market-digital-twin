"""F100 deep-dive panel — embedded JSON + a self-contained inline script.
No external assets. The script builds the slide-in panel from #dd-data on click."""
from __future__ import annotations

import json


def deepdive_json(targets) -> str:
    # ensure_ascii keeps it single-byte; escape '<' so the blob can't break out
    # of the <script> or inject markup.
    blob = json.dumps(targets, ensure_ascii=True).replace("<", "\\u003c")
    return f'<script type="application/json" id="dd-data">{blob}</script>'


_PANEL = """
<div class="dd-scrim" id="dd-scrim" onclick="closeDD()"></div>
<aside class="dd-drawer" id="dd-drawer" aria-hidden="true">
  <button class="dd-close" onclick="closeDD()" aria-label="Close">×</button>
  <div id="dd-head"></div><div id="dd-body"></div>
</aside>
<script>
(function(){
  var DATA={};
  try{DATA=JSON.parse(document.getElementById('dd-data').textContent);}catch(e){}
  function esc(s){var d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
  function spark(v,good){
    if(!v||!v.length)return '';
    var w=420,h=48,mn=Math.min.apply(0,v),mx=Math.max.apply(0,v),r=(mx-mn)||1,c=good?'#2e7d32':'#c0632a';
    var p=v.map(function(y,i){return (i/(v.length-1)*w).toFixed(0)+','+(h-4-(y-mn)/r*(h-10)).toFixed(0);}).join(' ');
    return '<svg viewBox="0 0 '+w+' '+h+'" width="100%" height="'+h+'"><polyline fill="none" stroke="'+c+'" stroke-width="2.5" points="'+p+'"/></svg>';
  }
  window.openDD=function(k){
    var d=DATA[k];if(!d)return;
    var tone={good:'#e6f4ea',bad:'#fdeae6',neutral:'#f0f2f5'},ink={good:'#1e7a34',bad:'#b23a12',neutral:'#555'};
    var bd=(d.badges||[]).map(function(b){return '<span class="dd-badge" style="background:'+tone[b.tone]+';color:'+ink[b.tone]+'">'+esc(b.text)+'</span>';}).join('');
    document.getElementById('dd-head').innerHTML='<div class="dd-eyebrow">'+esc(d.eyebrow)+'</div><div class="dd-title">'+esc(d.title)+'</div>'+bd;
    var h='';
    if(d.why){h+='<div class="dd-l">Why it\\'s rated this way</div><p class="dd-why">'+esc(d.why)+'</p>';}
    if(d.trend&&d.trend.length){h+='<div class="dd-l">Trend</div>'+spark(d.trend,d.trend_good);}
    if(d.evidence&&d.evidence.length){h+='<div class="dd-l">Evidence ('+d.evidence.length+')</div>';
      d.evidence.forEach(function(e){var a=/^https?:/.test(e.url||'')?' <a href="'+esc(e.url)+'">open source \\u2192</a>':'';
        h+='<div class="dd-ev"><b>'+esc(e.source)+'</b> <span class="dd-t">'+esc(e.trend)+'</span><div>'+esc(e.text)+'</div>'+a+'</div>';});}
    if(d.confidence){h+='<div class="dd-l">Confidence</div><div class="dd-box">'+esc(d.confidence)+'</div>';}
    if(d.change){h+='<div class="dd-l">What would change our mind</div><div class="dd-box">'+esc(d.change)+'</div>';}
    if(d.tsmc&&d.tsmc.length){h+='<div class="dd-l">What this means for TSMC</div>';
      d.tsmc.forEach(function(t){h+='<p class="dd-why">'+esc(t)+'</p>';});}
    if(d.calls&&d.calls.length){h+='<div class="dd-l">Standing calls</div>';
      d.calls.forEach(function(c){h+='<div class="dd-ev"><b>'+esc(c.title)+'</b> \\u2014 '+esc(c.verdict)+'<div class="dd-t">'+esc(c.trigger)+'</div></div>';});}
    document.getElementById('dd-body').innerHTML=h;
    document.getElementById('dd-scrim').classList.add('open');
    var dr=document.getElementById('dd-drawer');dr.classList.add('open');dr.setAttribute('aria-hidden','false');
  };
  window.closeDD=function(){
    document.getElementById('dd-scrim').classList.remove('open');
    var dr=document.getElementById('dd-drawer');dr.classList.remove('open');dr.setAttribute('aria-hidden','true');
  };
  document.addEventListener('keydown',function(e){if(e.key==='Escape')closeDD();});
})();
</script>
"""


def render_deepdive_panel() -> str:
    return _PANEL
