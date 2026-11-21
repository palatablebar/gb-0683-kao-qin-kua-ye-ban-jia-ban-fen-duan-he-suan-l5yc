'use strict';
const month = new URLSearchParams(location.search).get('month') || '2026-10';
const msg = document.getElementById('message');
function note(text){ if (msg) msg.textContent = text; }
async function call(url, options, okText){
  try{
    const resp = await fetch(url, Object.assign({headers:{'Content-Type':'application/json'}}, options));
    const body = await resp.json();
    if(!resp.ok) throw new Error(body.message || body.code);
    note(okText); location.reload();
  }catch(err){ note(err.message); }
}
const form = document.getElementById('source-form');
if(form) form.addEventListener('submit', e=>{
  e.preventDefault();
  const fd = new FormData(form);
  call('/api/m8_ledger/sources', {method:'POST', body:JSON.stringify({
    month, name: fd.get('name'), csv: fd.get('csv')})}, '来源已登记，请重算');
});
const rebuild = document.getElementById('rebuild');
if(rebuild) rebuild.addEventListener('click', ()=> call('/api/m8_ledger/datasets',
  {method:'POST', body:JSON.stringify({month, parameters:{}})}, '月度数据集已重算'));
const review = document.getElementById('review');
if(review) review.addEventListener('click', ()=> call(`/api/m8_ledger/datasets/${review.dataset.id}/review`,
  {method:'POST', body:JSON.stringify({month, version:Number(review.dataset.version), decision:'通过'})}, '复核通过'));
const publish = document.getElementById('publish');
if(publish) publish.addEventListener('click', ()=> call(`/api/m8_ledger/datasets/${publish.dataset.id}/publish`,
  {method:'POST', body:JSON.stringify({month})}, '本月结果已发布'));
