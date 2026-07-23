"""F101 Phase A: render the narrative category page."""
from __future__ import annotations

import json

from gpu_agent.dashboard.render import esc  # noqa: F401  (used from Task 6 on)


def evidence_json(evidence: dict) -> str:
    payload = json.dumps(evidence, ensure_ascii=True).replace("<", "\\u003c")
    return f'<script type="application/json" id="ev-data">{payload}</script>'


_PANEL = r"""<script>(function(){
var data={};try{data=JSON.parse(document.getElementById('ev-data').textContent);}catch(e){}
function el(t,c,x){var n=document.createElement(t);if(c)n.className=c;if(x!=null)n.textContent=x;return n;}
function spark(vals){if(!vals||vals.length<2)return null;
var w=120,h=28,lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals),sp=(hi-lo)||1,p=[];
for(var i=0;i<vals.length;i++){p.push((4+i*(w-8)/(vals.length-1)).toFixed(1)+','+(h-4-(vals[i]-lo)/sp*(h-8)).toFixed(1));}
var s=document.createElementNS('http://www.w3.org/2000/svg','svg');
s.setAttribute('viewBox','0 0 '+w+' '+h);s.setAttribute('class','ev-spark');
var pl=document.createElementNS('http://www.w3.org/2000/svg','polyline');
pl.setAttribute('points',p.join(' '));pl.setAttribute('fill','none');
pl.setAttribute('stroke','currentColor');pl.setAttribute('stroke-width','1.5');
s.appendChild(pl);return s;}
var scrim=el('div','ev-scrim'),panel=el('aside','ev-panel');
scrim.onclick=closeEV;document.body.appendChild(scrim);document.body.appendChild(panel);
window.openEV=function(k){var d=data[k];if(!d)return;panel.innerHTML='';
var x=el('button','ev-close','×');x.onclick=closeEV;panel.appendChild(x);
panel.appendChild(el('h3','ev-title',d.title||''));
panel.appendChild(el('p','ev-claim',d.claim_text||''));
if(d.series&&d.series.length>1){var sv=spark(d.series);if(sv)panel.appendChild(sv);}
var list=el('div','ev-chain');list.appendChild(el('div','ev-step','What we collected → where it came from'));
(d.findings||[]).forEach(function(f){var row=el('div','ev-row');
row.appendChild(el('span','ev-src',(f.source||'')+' · '+(f.date||'')));
row.appendChild(el('span','ev-take',f.take||''));
if(f.url&&/^https?:/.test(f.url)){var a=el('a','ev-link','↗');
a.href=encodeURI(f.url);a.target='_blank';a.rel='noopener';row.appendChild(a);}
list.appendChild(row);});panel.appendChild(list);
if(d.explore){var ex=el('a','ev-explore','see everything we have →');
ex.href=encodeURI(d.explore);panel.appendChild(ex);}
scrim.classList.add('on');panel.classList.add('on');};
window.closeEV=function(){scrim.classList.remove('on');panel.classList.remove('on');};
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeEV();});
document.addEventListener('click',function(e){var t=e.target.closest&&e.target.closest('[data-ev]');
if(t){e.preventDefault();openEV(t.getAttribute('data-ev'));}});
})();</script>"""


def render_evidence_panel() -> str:
    return _PANEL
