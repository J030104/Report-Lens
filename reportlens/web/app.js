const token = new URL(location.href).searchParams.get('token') || '';
const $ = id => document.getElementById(id);
let manifest = null, visible = [], selected = 0, view = 'diff', generation = -1, busy = false, statusTimer;
const url = path => `${path}${path.includes('?')?'&':'?'}token=${encodeURIComponent(token)}`;
async function api(path, data, raw=false) {
  const response = await fetch(url(path), data===undefined ? {} : {method:'POST', headers:raw?{}:{'Content-Type':'application/json'},body:raw?data:JSON.stringify(data)});
  const value = await response.json(); if(!response.ok) throw new Error(value.error || 'Request failed'); return value;
}
function error(e) { $('status').textContent = e.message; $('status').className='error'; }
const short = info => info?.commit ? info.commit.slice(0,8) : 'PDF';
async function versions(setDefaults=false) {
  const data = await api('/api/versions');
  for(const side of ['before','after']) {
    const old = $(side).value; $(side).replaceChildren();
    for(const item of data.versions) {
      const option = document.createElement('option'); option.value=item.commit;
      option.textContent=`${item.commit.slice(0,8)} · ${item.label}`; $(side).append(option);
    }
    $(side).value=setDefaults ? (data.defaults[side==='before'?1:0]?.commit || '') : old;
  }
}
function textEdits(pair) {
  return manifest.edits.filter(e => e.before_pages.includes(pair.before) || e.after_pages.includes(pair.after));
}
function filterPages(reset=false) {
  if(!manifest) return;
  const filter=$('filter').value, search=$('search').value.toLocaleLowerCase();
  visible=manifest.pairs.filter(p => (filter==='all'||filter==='changed'&&p.changed||filter==='text'&&(p.added||p.removed)||filter==='objects'&&p.changed&&p.hints.length||filter==='visual'&&p.kind==='visual / layout') && (!search||`${p.title} ${p.before} ${p.after} ${textEdits(p).map(e=>e.added+' '+e.removed).join(' ')}`.toLocaleLowerCase().includes(search)));
  if(reset || !visible.some(p=>p.id===selected)) selected=visible[0]?.id??-1;
  $('pages').replaceChildren();
  for(const pair of visible) {
    const button=document.createElement('button'); button.className='page-item'+(pair.id===selected?' active':'');
    button.setAttribute('aria-current',pair.id===selected?'true':'false');
    const row=document.createElement('span'); row.className='row';
    const label=document.createElement('span'); label.textContent=`Page ${pair.before??'—'} → ${pair.after??'—'}`;
    const numbers=document.createElement('span'); numbers.className='numbers'; numbers.textContent=`+${pair.added} −${pair.removed}`;
    row.append(label,numbers); const title=document.createElement('span'); title.className='title'; title.textContent=pair.title;
    const tag=document.createElement('span'); tag.className='tag'; tag.textContent=[pair.kind,...pair.hints].join(' · ');
    button.append(row,title,tag); button.onclick=()=>{selected=pair.id;filterPages();}; $('pages').append(button);
  }
  render();
}
function render() {
  if(!manifest) return;
  const pair=visible.find(p=>p.id===selected);
  $('canvas').replaceChildren(); $('edits').replaceChildren();
  $('position').textContent=`${pair?visible.indexOf(pair)+1:0} / ${visible.length}`;
  $('prev').disabled=!pair||visible.indexOf(pair)===0; $('next').disabled=!pair||visible.indexOf(pair)===visible.length-1;
  $('text-panel').hidden=!pair||view!=='diff';
  if(!pair) {
    const note=document.createElement('p'); note.className='welcome'; note.textContent='No pages match this filter. Choose All pages to browse the report.'; $('canvas').append(note); return;
  }
  $('heading').textContent=`Page ${pair.before??'—'} → ${pair.after??'—'}`;
  $('comparison-label').textContent=pair.kind.toUpperCase();
  const sides=view==='diff'?['before','after']:[view];
  const zoom=$('zoom').value;
  $('canvas').className='canvas'+(view!=='diff'?' single':'')+(zoom!=='fit'?' zoomed':'');
  for(const side of sides) {
    const column=document.createElement('div'); column.className='page-column';
    const heading=document.createElement('div'); heading.className='page-label '+(side==='before'?'removed':'added');
    const label=document.createElement('span'); label.textContent=side==='before'?'− BEFORE':'＋ AFTER';
    const hash=document.createElement('span'); hash.className='pill'; hash.textContent=short(manifest[side]); heading.append(label,hash); column.append(heading);
    const number=pair[side];
    if(number!==null) {
      const page=manifest.pages[side][number-1], image=document.createElement('img'); image.className='paper';
      image.alt=`Complete ${side} page ${number}${view==='diff'?', with text changes highlighted':''}`;
      image.src=url('/assets/'+manifest.session+'/'+page[view==='diff'?'diff_image':'image'].split('/').pop());
      if(zoom==='page') {
        const workspace=$('canvas').parentElement;
        const height=Math.max(300,Math.min(window.innerHeight,workspace.clientHeight)-workspace.querySelector('.review-header').offsetHeight-workspace.querySelector('.toolbar').offsetHeight-86);
        const width=($('canvas').clientWidth-80)/sides.length;
        column.style.width=`${Math.min(width,height*page.width/page.height)}px`;
      } else if(zoom!=='fit') column.style.width=`${page.width*Number(zoom)/100*96/72}px`;
      column.append(image);
    } else { const empty=document.createElement('div'); empty.className='page-empty'; empty.textContent=side==='before'?'This page was added.':'This page was removed.'; column.append(empty); }
    $('canvas').append(column);
  }
  const edits=textEdits(pair); $('edit-count').textContent=`(${edits.length})`;
  for(const edit of edits) {
    const row=document.createElement('div'); row.className='edit';
    for(const kind of ['removed','added']) {
      const cell=document.createElement('div'), text=document.createElement(kind==='removed'?'del':'ins');
      text.textContent=edit[kind]||'—'; cell.append(text); row.append(cell);
    } $('edits').append(row);
  }
  if(!edits.length) { const note=document.createElement('p'); note.className='empty-edits'; note.textContent=pair.changed?'No extracted text edits on these pages. Inspect the complete Before/After views for visual or layout changes.':'No changes detected on these pages.'; $('edits').append(note); }
  document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('selected',b.dataset.view===view);b.setAttribute('aria-pressed',String(b.dataset.view===view));});
}
async function load() {
  manifest=await api('/api/manifest'); if(!manifest) return;
  const s=manifest.summary; $('count').textContent=s.changed_pairs;
  $('stats').children[0].textContent=`+${s.added_words} added`; $('stats').children[1].textContent=`−${s.removed_words} removed`;
  $('subtitle').textContent=`${manifest.before.label} → ${manifest.after.label}`;
  $('notes').textContent=manifest.notes.join(' ');
  for(const [id,path] of [['download-package','package'],['download-pdf','diff']]) { $(id).href=url('/download/'+path+'?session='+manifest.session); $(id).hidden=false; }
  $('download-pdf').textContent=manifest.pdf_export?.layout==='latex'?'Export LaTeX PDF ↗':'Export PDF ↗';
  if(manifest.before.commit) $('before').value=manifest.before.commit;
  if(manifest.after.commit) $('after').value=manifest.after.commit;
  filterPages(true);
}
async function poll() {
  try {
    const state=await api('/api/status'); busy=state.busy;
    $('status').textContent=state.error||state.message+ (state.monitor?' · Watching for report commits':'');
    $('status').className=state.error?'error':busy?'busy':'';
    $('revisions').hidden=!state.has_repository; $('watch').checked=state.monitor;
    for(const id of ['compare','latest','swap','open']) $(id).disabled=busy;
    if(state.generation!==generation) { generation=state.generation; await versions(); await load(); }
  } catch(e) {error(e);} finally {statusTimer=setTimeout(poll,2000);}
}
$('compare').onclick=()=>api('/api/compare',{before:$('before').value,after:$('after').value}).catch(error);
$('latest').onclick=async()=>{try{await versions(true);await api('/api/compare',{});}catch(e){error(e);}};
$('swap').onclick=()=>{const old=$('before').value;$('before').value=$('after').value;$('after').value=old;};
$('watch').onchange=()=>api('/api/monitor',{enabled:$('watch').checked}).catch(error);
$('open').onclick=()=>$('file').click();
$('file').onchange=async()=>{if(!$('file').files.length)return;try{await api('/api/open',$('file').files[0],true);}catch(e){error(e);}finally{$('file').value='';}};
$('search').oninput=()=>filterPages(true); $('filter').onchange=()=>filterPages(true); $('zoom').onchange=render;
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{view=b.dataset.view;render();});
function move(offset){const i=visible.findIndex(p=>p.id===selected)+offset;if(i>=0&&i<visible.length){selected=visible[i].id;filterPages();}}
$('prev').onclick=()=>move(-1);$('next').onclick=()=>move(1);
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName))return;if(e.key==='ArrowLeft')move(-1);if(e.key==='ArrowRight')move(1);});
window.addEventListener('resize',()=>{if($('zoom').value==='page')render();});
versions(true).then(poll).catch(error);
