(() => {
  const rows=[...document.querySelectorAll('.portainer-row')], search=document.getElementById('portainerFilter'), env=document.getElementById('environmentFilter'), all=document.getElementById('selectAllPortainer'), count=document.getElementById('portainerSelectedCount');
  if(!rows.length) return;
  let page=1, pageSize=Number(localStorage.getItem('softwareReleaseRadarPortainerPageSize')||25);
  if(![10,25,50,100,200].includes(pageSize)) pageSize=25;
  const matches=()=>{const q=(search.value||'').trim().toLowerCase(), e=(env.value||'').trim().toLowerCase();return rows.filter(row=>(!q||row.dataset.search.includes(q))&&(!e||row.dataset.environment===e));};
  const visibleBoxes=()=>rows.filter(row=>!row.hidden).map(row=>row.querySelector('.portainer-checkbox'));
  const updateSelection=()=>{const selected=document.querySelectorAll('.portainer-checkbox:checked').length;count.textContent=`${selected} selected`;const visible=visibleBoxes();all.checked=visible.length>0&&visible.every(box=>box.checked);all.indeterminate=visible.some(box=>box.checked)&&!all.checked;};
  const render=(reset=false)=>{if(reset)page=1;const filtered=matches(),pages=Math.max(1,Math.ceil(filtered.length/pageSize));page=Math.min(Math.max(1,page),pages);const start=(page-1)*pageSize,end=Math.min(start+pageSize,filtered.length),shown=new Set(filtered.slice(start,end));rows.forEach(row=>row.hidden=!shown.has(row));document.getElementById('portainer-page-info').textContent=filtered.length?`Showing ${start+1}–${end} of ${filtered.length} matching containers`:'No matching containers';document.getElementById('portainer-page-label').textContent=`Page ${page} of ${pages}`;document.getElementById('portainer-first').disabled=page<=1;document.getElementById('portainer-prev').disabled=page<=1;document.getElementById('portainer-next').disabled=page>=pages;document.getElementById('portainer-last').disabled=page>=pages;updateSelection();};
  const size=document.getElementById('portainer-page-size');size.value=String(pageSize);size.addEventListener('change',()=>{pageSize=Number(size.value);localStorage.setItem('softwareReleaseRadarPortainerPageSize',String(pageSize));render(true);});
  search.addEventListener('input',()=>render(true));env.addEventListener('change',()=>render(true));all.addEventListener('change',()=>{visibleBoxes().forEach(box=>box.checked=all.checked);updateSelection();});document.querySelectorAll('.portainer-checkbox').forEach(box=>box.addEventListener('change',updateSelection));document.getElementById('portainer-first').addEventListener('click',()=>{page=1;render();});document.getElementById('portainer-prev').addEventListener('click',()=>{page-=1;render();});document.getElementById('portainer-next').addEventListener('click',()=>{page+=1;render();});document.getElementById('portainer-last').addEventListener('click',()=>{page=Math.ceil(matches().length/pageSize)||1;render();});render();
})();

(() => {
  const panel=document.getElementById('portainer-sync-progress'); if(!panel) return;
  const terminal=new Set(['completed','failed']); let prior=panel.querySelector('#sync-status').textContent.trim();
  const update=(j)=>{
    const total=Number(j.total_environments||0), done=Number(j.processed_environments||0);
    document.getElementById('sync-status').textContent=j.status||'unknown';
    document.getElementById('sync-message').textContent=j.message||j.status||'';
    document.getElementById('sync-progress-bar').style.width=`${total?Math.min(100,done*100/total):0}%`;
    document.getElementById('sync-processed').textContent=done; document.getElementById('sync-total').textContent=total;
    document.getElementById('sync-services').textContent=j.services_found||0; document.getElementById('sync-offline').textContent=j.offline_environments||0; document.getElementById('sync-errors').textContent=j.unexpected_errors||0;
    document.getElementById('sync-current').textContent=j.current_environment||'';
    const error=document.getElementById('sync-error'); error.textContent=j.error||''; error.hidden=!j.error;
    if(terminal.has(j.status)&&!terminal.has(prior)){setTimeout(()=>location.reload(),1200)} prior=j.status;
  };
  const poll=async()=>{try{const r=await fetch(panel.dataset.statusUrl,{headers:{Accept:'application/json'},cache:'no-store'});if(r.ok)update(await r.json())}catch(e){} if(!terminal.has(prior))setTimeout(poll,2000)};
  if(!terminal.has(prior))setTimeout(poll,1000);
})();

(() => {
  const panel=document.getElementById('portainer-import-progress'); if(!panel) return;
  const terminal=new Set(['completed','failed']); let prior=panel.querySelector('#import-status').textContent.trim();
  const update=(job)=>{
    const total=Number(job.total_items||0), done=Number(job.processed_items||0);
    document.getElementById('import-status').textContent=job.status||'unknown';
    document.getElementById('import-message').textContent=job.message||job.status||'';
    document.getElementById('import-progress-bar').style.width=`${total?Math.min(100,done*100/total):0}%`;
    document.getElementById('import-processed').textContent=done;
    document.getElementById('import-total').textContent=total;
    document.getElementById('import-imported').textContent=job.imported_items||0;
    document.getElementById('import-failed').textContent=job.failed_items||0;
    document.getElementById('import-current').textContent=job.current_item||'';
    const error=document.getElementById('import-error'); error.textContent=job.error||''; error.hidden=!job.error;
    if(terminal.has(job.status)&&!terminal.has(prior)){setTimeout(()=>location.reload(),1200)}
    prior=job.status;
  };
  const poll=async()=>{try{const response=await fetch(panel.dataset.statusUrl,{headers:{Accept:'application/json'},cache:'no-store'});if(response.ok)update(await response.json())}catch(error){}if(!terminal.has(prior))setTimeout(poll,1500)};
  if(!terminal.has(prior))setTimeout(poll,700);
})();
