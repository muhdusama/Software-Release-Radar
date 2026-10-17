function showProbeFields(){const mode=document.getElementById('probe-mode').value;document.querySelectorAll('.http-probe-field').forEach(e=>e.hidden=!['http_auto','http_json','http_regex'].includes(mode));document.querySelectorAll('.json-probe-field').forEach(e=>e.hidden=mode!=='http_json');document.querySelectorAll('.regex-probe-field').forEach(e=>e.hidden=mode!=='http_regex');document.querySelectorAll('.ssh-probe-field').forEach(e=>e.hidden=mode!=='ssh_docker');}
showProbeFields();
document.getElementById('probe-mode').addEventListener('change', showProbeFields);
