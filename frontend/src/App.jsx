import { useState, useRef } from "react";

const C = { bg0:"#0A0A08",bg1:"#111110",bg2:"#1A1918",bg3:"#222120",border:"#2C2A28",borderL:"#3A3836",tx:"#D4D0CB",txD:"#8A8580",txM:"#5E5A55",txB:"#EDE9E4",ac:"#C8965A",acD:"#A0784A",acBg:"rgba(200,150,90,.08)",g:"#2ECC71",gB:"rgba(46,204,113,.1)",y:"#F1C40F",yB:"rgba(241,196,15,.1)",r:"#E74C3C",rB:"rgba(231,76,60,.1)",b:"#3498DB",bB:"rgba(52,152,219,.1)" };
const F = `"IBM Plex Sans",system-ui,sans-serif`, M = `"IBM Plex Mono","Consolas",monospace`;

const ago=(iso)=>{if(!iso)return"—";const m=Math.floor((Date.now()-new Date(iso))/60000);if(m<1)return"now";if(m<60)return m+"m";const h=Math.floor(m/60);return h<24?h+"h":Math.floor(h/24)+"d"};
const fDate=(iso)=>iso?new Date(iso).toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"}):"—";
const fTime=(iso)=>iso?new Date(iso).toLocaleString("en-US",{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"}):"—";
const fBytes=(b)=>{if(!b)return"—";if(b>1e9)return(b/1e9).toFixed(1)+" GB";if(b>1e6)return(b/1e6).toFixed(0)+" MB";return(b/1024).toFixed(0)+" KB"};
const sc=(s)=>({healthy:C.g,registered:C.g,online:C.g,available:C.g,pass:C.g,warning:C.y,degraded:C.y,warn:C.y,error:C.r,unregistered:C.r,offline:C.r,unavailable:C.r,critical:C.r,fail:C.r,info:C.b,skip:C.txM,untested:C.txM}[s]||C.txM);
const sbg=(s)=>({healthy:C.gB,registered:C.gB,online:C.gB,available:C.gB,pass:C.gB,warning:C.yB,degraded:C.yB,warn:C.yB,error:C.rB,unregistered:C.rB,offline:C.rB,unavailable:C.rB,critical:C.rB,fail:C.rB,info:C.bB}[s]||"rgba(94,90,85,.06)");

const Pill=({status,label})=><span style={{display:"inline-flex",alignItems:"center",gap:5,padding:"2px 10px",borderRadius:99,fontSize:11,fontWeight:600,letterSpacing:".04em",textTransform:"uppercase",color:sc(status),background:sbg(status),whiteSpace:"nowrap"}}><span style={{width:6,height:6,borderRadius:"50%",background:sc(status)}}/>{label||status}</span>;
const Stat=({l,v,c})=><div style={{textAlign:"center"}}><div style={{fontSize:20,fontWeight:700,color:c||C.txB,fontFamily:M}}>{v}</div><div style={{fontSize:9,color:C.txM,textTransform:"uppercase",letterSpacing:".06em",marginTop:3,fontWeight:600}}>{l}</div></div>;
const Sv=({d,s=18,c="currentColor"})=><svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={d}/></svg>;

const iCk="M5 13l4 4L19 7",iX="M6 18L18 6M6 6l12 12",iDl="M12 4v12m0 0l-4-4m4 4l4-4M4 18h16",iRf="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15",iP="M12 4v16m8-8H4",iLk="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z",iSh="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",iW="M12 9v2m0 4h.01M5.07 19h13.86c1.54 0 2.5-1.67 1.73-3L13.73 4c-.77-1.33-2.69-1.33-3.46 0L3.34 16c-.77 1.33.19 3 1.73 3z",iEye="M15 12a3 3 0 11-6 0 3 3 0 016 0zM2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z",iEyeX="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M3 3l18 18";

function Btn({children,variant="default",onClick,small,disabled,loading,style:sx,type}){const[h,setH]=useState(false);const v={default:{bg:C.bg3,bh:"#2E2C2A",bc:C.borderL,c:C.tx},primary:{bg:"#1B6B3A",bh:"#1E8045",bc:"#1B6B3A",c:"#fff"},danger:{bg:"#6B1A1A",bh:"#801F1F",bc:"#6B1A1A",c:"#FCA5A5"},ghost:{bg:"transparent",bh:"rgba(255,255,255,.04)",bc:"transparent",c:C.txD},accent:{bg:C.acD,bh:C.ac,bc:C.acD,c:"#fff"}}[variant];return<button type={type||"button"} onClick={onClick} disabled={disabled||loading} onMouseEnter={()=>setH(true)} onMouseLeave={()=>setH(false)} style={{display:"inline-flex",alignItems:"center",justifyContent:"center",gap:6,padding:small?"5px 12px":"9px 18px",fontSize:small?12:13,fontWeight:600,background:disabled?C.bg2:h?v.bh:v.bg,border:"1px solid "+(disabled?C.border:v.bc),borderRadius:6,color:disabled?C.txM:v.c,cursor:disabled?"not-allowed":"pointer",transition:"all .12s",fontFamily:F,opacity:disabled?.5:1,...sx}}>{loading&&<span style={{display:"inline-block",width:14,height:14,border:"2px solid rgba(255,255,255,.2)",borderTopColor:"#fff",borderRadius:"50%",animation:"spin .6s linear infinite"}}/>}{children}</button>}

function Card({children,style,onClick,hv}){const[h,setH]=useState(false);return<div onClick={onClick} onMouseEnter={()=>setH(true)} onMouseLeave={()=>setH(false)} style={{background:h&&hv?C.bg3:C.bg2,border:"1px solid "+C.border,borderRadius:8,padding:20,cursor:onClick?"pointer":"default",transition:"all .15s",transform:h&&hv?"translateY(-1px)":"none",boxShadow:h&&hv?"0 6px 24px rgba(0,0,0,.4)":"none",...style}}>{children}</div>}

function Table({cols,data}){return<div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}><thead><tr>{cols.map(c=><th key={c.k} style={{textAlign:"left",padding:"10px 14px",borderBottom:"1px solid "+C.border,fontSize:10,textTransform:"uppercase",letterSpacing:".06em",color:C.txM,fontWeight:700}}>{c.l}</th>)}</tr></thead><tbody>{data.map((r,i)=><tr key={i} style={{borderBottom:"1px solid rgba(44,42,40,.4)"}}>{cols.map(c=><td key={c.k} style={{padding:"10px 14px",color:C.tx}}>{c.r?c.r(r[c.k],r):(r[c.k]||"—")}</td>)}</tr>)}{data.length===0&&<tr><td colSpan={cols.length} style={{padding:40,textAlign:"center",color:C.txM}}>No data</td></tr>}</tbody></table></div>}

function Input({label,value,onChange,type="text",placeholder,help,error,mono,required,icon}){const[show,setShow]=useState(false);const isPass=type==="password";return<div style={{marginBottom:16}}><label style={{display:"block",fontSize:11,fontWeight:600,color:C.txD,textTransform:"uppercase",letterSpacing:".05em",marginBottom:5}}>{label}{required&&<span style={{color:C.r}}>*</span>}</label><div style={{position:"relative"}}><input type={isPass&&show?"text":type} value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder} style={{width:"100%",padding:"9px 12px",paddingRight:isPass?36:12,fontSize:13,fontFamily:mono?M:F,background:C.bg1,border:"1px solid "+(error?C.r:C.border),borderRadius:6,color:C.txB,outline:"none",boxSizing:"border-box",transition:"border-color .15s"}} onFocus={e=>e.target.style.borderColor=C.ac} onBlur={e=>e.target.style.borderColor=error?C.r:C.border}/>{isPass&&<button type="button" onClick={()=>setShow(!show)} style={{position:"absolute",right:8,top:"50%",transform:"translateY(-50%)",background:"none",border:"none",cursor:"pointer",padding:2}}><Sv d={show?iEyeX:iEye} s={16} c={C.txM}/></button>}</div>{help&&!error&&<div style={{fontSize:11,color:C.txM,marginTop:3}}>{help}</div>}{error&&<div style={{fontSize:11,color:C.r,marginTop:3}}>{error}</div>}</div>}

function Select({label,value,onChange,options,help}){return<div style={{marginBottom:16}}><label style={{display:"block",fontSize:11,fontWeight:600,color:C.txD,textTransform:"uppercase",letterSpacing:".05em",marginBottom:5}}>{label}</label><select value={value} onChange={e=>onChange(e.target.value)} style={{width:"100%",padding:"9px 12px",fontSize:13,fontFamily:F,background:C.bg1,border:"1px solid "+C.border,borderRadius:6,color:C.txB,outline:"none",cursor:"pointer"}}>{options.map(o=><option key={o.v} value={o.v}>{o.l}</option>)}</select>{help&&<div style={{fontSize:11,color:C.txM,marginTop:3}}>{help}</div>}</div>}

/* ═══════════════════════════════════════════════════════════════════════════
   ADD INSTANCE MODAL — Test Connection + Save
   ═══════════════════════════════════════════════════════════════════════════ */
function AddInstanceModal({onClose,onSave}){
  const[step,setStep]=useState("form"); // form → testing → results → saving
  const[form,setForm]=useState({name:"",base_url:"https://",username:"admin",password:"",tls_policy:"verify",poll_interval_s:60,notes:""});
  const[errors,setErrors]=useState({});
  const[testResult,setTestResult]=useState(null);
  const[testSteps,setTestSteps]=useState([]);
  const[saving,setSaving]=useState(false);
  const upd=(k,v)=>setForm(p=>({...p,[k]:v}));

  const validate=()=>{
    const e={};
    if(!form.name.trim()||form.name.length<2)e.name="Name must be at least 2 characters";
    if(!form.base_url.startsWith("https://"))e.base_url="Must start with https://";
    if(form.base_url.length<10)e.base_url="Enter a valid URL";
    if(!form.username.trim())e.username="Required";
    if(!form.password)e.password="Required";
    setErrors(e);
    return Object.keys(e).length===0;
  };

  const runTest=async()=>{
    if(!validate())return;
    setStep("testing");setTestSteps([]);setTestResult(null);

    // Simulate the multi-step test connection process
    // In production, this calls POST /api/pbx/test-connection
    const steps = [];
    const addStep=(s)=>{steps.push(s);setTestSteps([...steps])};

    await new Promise(r=>setTimeout(r,400));
    addStep({step:"tls_connect",status:"pass",message:`HTTPS connection to ${form.base_url} successful (142ms)`,duration_ms:142});

    await new Promise(r=>setTimeout(r,600));
    if(form.password.length<3){
      addStep({step:"authenticate",status:"fail",message:"Invalid credentials — HTTP 401",duration_ms:89});
      setTestResult({success:false,message:"Authentication failed. Check username and password."});
      setStep("results");
      return;
    }
    addStep({step:"authenticate",status:"pass",message:"Login successful via webclient_token (89ms)",duration_ms:89});

    await new Promise(r=>setTimeout(r,400));
    addStep({step:"version_detect",status:"pass",message:"Detected version: 20.0.3.884",duration_ms:45});

    await new Promise(r=>setTimeout(r,300));
    addStep({step:"probe_trunks",status:"pass",message:"trunks: ✓ available via api_json",duration_ms:67});
    await new Promise(r=>setTimeout(r,200));
    addStep({step:"probe_sbcs",status:"pass",message:"sbcs: ✓ available via api_json",duration_ms:52});
    await new Promise(r=>setTimeout(r,200));
    addStep({step:"probe_license",status:"pass",message:"license: ✓ available via api_json",duration_ms:38});
    await new Promise(r=>setTimeout(r,200));
    addStep({step:"probe_backup_list",status:"pass",message:"backup_list: ✓ available via api_json",duration_ms:41});

    setTestResult({
      success:true,
      version:"20.0.3.884",
      message:"All systems operational — ready to monitor",
      capabilities:[
        {feature:"trunks",status:"available",method:"api_json"},
        {feature:"sbcs",status:"available",method:"api_json"},
        {feature:"license",status:"available",method:"api_json"},
        {feature:"backup_list",status:"available",method:"api_json"},
      ]
    });
    setStep("results");
  };

  const saveInstance=async()=>{
    setSaving(true);
    // In production: POST /api/pbx/instances with form + testResult.capabilities
    await new Promise(r=>setTimeout(r,500));
    onSave({
      id:crypto.randomUUID(),name:form.name,base_url:form.base_url,
      version:testResult?.version||null,status:"healthy",
      last_seen:new Date().toISOString(),credential_username:form.username,
      trunks:[],sbcs:[],license:{edition:"—",expiry:null,calls:0,valid:null,warnings:[]},
      backups:[],caps:Object.fromEntries((testResult?.capabilities||[]).map(c=>[c.feature,c.status]))
    });
    setSaving(false);
    onClose();
  };

  return<div style={{position:"fixed",inset:0,zIndex:1000,display:"flex",alignItems:"center",justifyContent:"center"}}>
    <div style={{position:"absolute",inset:0,background:"rgba(0,0,0,.7)",backdropFilter:"blur(4px)"}} onClick={onClose}/>
    <div style={{position:"relative",background:C.bg1,border:"1px solid "+C.border,borderRadius:12,width:560,maxHeight:"90vh",overflow:"auto",boxShadow:"0 20px 60px rgba(0,0,0,.6)"}}>
      {/* Header */}
      <div style={{padding:"20px 24px",borderBottom:"1px solid "+C.border,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
        <div>
          <div style={{fontSize:17,fontWeight:700,color:C.txB}}>Add PBX Instance</div>
          <div style={{fontSize:12,color:C.txM,marginTop:2}}>
            {step==="form"?"Enter connection details":step==="testing"?"Testing connectivity…":step==="results"?(testResult?.success?"Connection verified":"Connection failed"):""}
          </div>
        </div>
        <button onClick={onClose} style={{background:"none",border:"none",cursor:"pointer",padding:4}}><Sv d={iX} s={20} c={C.txM}/></button>
      </div>

      <div style={{padding:"20px 24px"}}>
        {/* ── FORM STEP ── */}
        {step==="form"&&<>
          {/* Security notice */}
          <div style={{display:"flex",gap:10,padding:12,background:C.acBg,border:"1px solid rgba(200,150,90,.15)",borderRadius:6,marginBottom:20,fontSize:12,color:C.ac}}>
            <Sv d={iSh} s={18} c={C.ac}/>
            <div><strong>Credentials encrypted at rest</strong> with AES-256-GCM. Passwords never stored in plaintext. Connection over HTTPS only.</div>
          </div>

          <Input label="Instance Name" value={form.name} onChange={v=>upd("name",v)} placeholder="e.g. HQ Production PBX" error={errors.name} required/>
          <Input label="PBX URL" value={form.base_url} onChange={v=>upd("base_url",v)} placeholder="https://pbx.example.com:5001" help="Full HTTPS URL to the 3CX management console" error={errors.base_url} mono required/>

          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
            <Input label="Admin Username" value={form.username} onChange={v=>upd("username",v)} placeholder="admin" error={errors.username} required/>
            <Input label="Password" value={form.password} onChange={v=>upd("password",v)} type="password" placeholder="••••••••" error={errors.password} required/>
          </div>

          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
            <Select label="TLS Verification" value={form.tls_policy} onChange={v=>upd("tls_policy",v)} options={[{v:"verify",l:"Verify Certificate (Recommended)"},{v:"trust_self_signed",l:"Trust Self-Signed"}]} help={form.tls_policy==="trust_self_signed"?"⚠ Less secure — only use for lab/dev":"Strict TLS certificate verification"}/>
            <Select label="Poll Interval" value={form.poll_interval_s} onChange={v=>upd("poll_interval_s",+v)} options={[{v:30,l:"30 seconds"},{v:60,l:"60 seconds (Recommended)"},{v:120,l:"2 minutes"},{v:300,l:"5 minutes"}]}/>
          </div>

          <Input label="Notes" value={form.notes} onChange={v=>upd("notes",v)} placeholder="Optional description or location…"/>

          {form.tls_policy==="trust_self_signed"&&<div style={{display:"flex",gap:10,padding:12,background:C.rB,border:"1px solid rgba(231,76,60,.2)",borderRadius:6,marginBottom:16,fontSize:12,color:C.r}}>
            <Sv d={iW} s={18} c={C.r}/>
            <div><strong>Self-signed certificate trust enabled.</strong> This disables TLS verification for this host. Only use for development or isolated lab environments. This will be logged in the audit trail.</div>
          </div>}

          <div style={{display:"flex",justifyContent:"flex-end",gap:10,paddingTop:8,borderTop:"1px solid "+C.border}}>
            <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
            <Btn variant="accent" onClick={runTest}><Sv d={iSh} s={14}/> Test Connection</Btn>
          </div>
        </>}

        {/* ── TESTING STEP ── */}
        {step==="testing"&&<div>
          <div style={{marginBottom:16,fontSize:13,color:C.txD}}>Validating connectivity and discovering capabilities…</div>
          {testSteps.map((s,i)=><div key={i} style={{display:"flex",alignItems:"flex-start",gap:10,padding:"8px 0",borderBottom:"1px solid rgba(44,42,40,.3)",animation:"fadeIn .3s ease"}}>
            <div style={{marginTop:2,flexShrink:0}}>
              {s.status==="pass"?<Sv d={iCk} s={16} c={C.g}/>:s.status==="fail"?<Sv d={iX} s={16} c={C.r}/>:<span style={{display:"inline-block",width:16,height:16,border:"2px solid "+C.txM,borderTopColor:C.ac,borderRadius:"50%",animation:"spin .6s linear infinite"}}/>}
            </div>
            <div style={{flex:1}}>
              <div style={{fontSize:12,fontWeight:600,color:s.status==="fail"?C.r:C.txB}}>{s.step.replace(/_/g," ")}</div>
              <div style={{fontSize:11,color:C.txD,marginTop:1,fontFamily:M}}>{s.message}</div>
            </div>
            {s.duration_ms>0&&<div style={{fontSize:10,color:C.txM,fontFamily:M,flexShrink:0}}>{s.duration_ms}ms</div>}
          </div>)}
          {!testResult&&<div style={{textAlign:"center",padding:16}}><span style={{display:"inline-block",width:20,height:20,border:"2px solid "+C.border,borderTopColor:C.ac,borderRadius:"50%",animation:"spin .6s linear infinite"}}/></div>}
        </div>}

        {/* ── RESULTS STEP ── */}
        {step==="results"&&<div>
          {/* Result banner */}
          <div style={{display:"flex",gap:12,padding:14,background:testResult.success?C.gB:C.rB,border:"1px solid "+(testResult.success?"rgba(46,204,113,.2)":"rgba(231,76,60,.2)"),borderRadius:8,marginBottom:18}}>
            <div style={{marginTop:1}}>{testResult.success?<Sv d={iCk} s={22} c={C.g}/>:<Sv d={iX} s={22} c={C.r}/>}</div>
            <div>
              <div style={{fontSize:15,fontWeight:700,color:testResult.success?C.g:C.r}}>{testResult.success?"Connection Successful":"Connection Failed"}</div>
              <div style={{fontSize:12,color:C.txD,marginTop:2}}>{testResult.message}</div>
              {testResult.version&&<div style={{fontSize:11,color:C.txM,marginTop:2,fontFamily:M}}>3CX Version: {testResult.version}</div>}
            </div>
          </div>

          {/* Capability matrix */}
          {testResult.capabilities?.length>0&&<div style={{marginBottom:18}}>
            <div style={{fontSize:11,fontWeight:700,color:C.txM,textTransform:"uppercase",letterSpacing:".05em",marginBottom:8}}>Capability Matrix</div>
            <div style={{display:"grid",gridTemplateColumns:"repeat(2,1fr)",gap:6}}>
              {testResult.capabilities.map((c,i)=><div key={i} style={{display:"flex",alignItems:"center",gap:8,padding:"8px 12px",background:C.bg0,borderRadius:6,border:"1px solid "+C.border}}>
                <span style={{width:8,height:8,borderRadius:"50%",background:sc(c.status)}}/>
                <span style={{fontSize:12,fontWeight:500,color:C.txB,textTransform:"capitalize"}}>{c.feature.replace(/_/g," ")}</span>
                <span style={{flex:1}}/>
                <span style={{fontSize:10,color:C.txM,fontFamily:M}}>{c.method||c.status}</span>
              </div>)}
            </div>
          </div>}

          {/* Test steps */}
          <details style={{marginBottom:18}}>
            <summary style={{fontSize:11,fontWeight:600,color:C.txM,cursor:"pointer",textTransform:"uppercase",letterSpacing:".05em"}}>Connection Steps ({testSteps.length})</summary>
            <div style={{marginTop:8}}>
              {testSteps.map((s,i)=><div key={i} style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0",fontSize:12}}>
                <span style={{width:6,height:6,borderRadius:"50%",background:sc(s.status)}}/>
                <span style={{color:C.txD,fontFamily:M}}>{s.message}</span>
              </div>)}
            </div>
          </details>

          <div style={{display:"flex",justifyContent:"flex-end",gap:10,paddingTop:12,borderTop:"1px solid "+C.border}}>
            <Btn variant="ghost" onClick={()=>{setStep("form");setTestResult(null);setTestSteps([])}}>← Edit Details</Btn>
            {!testResult.success&&<Btn variant="accent" onClick={runTest}><Sv d={iRf} s={14}/> Retry</Btn>}
            {testResult.success&&<Btn variant="primary" onClick={saveInstance} loading={saving}><Sv d={iCk} s={14}/> Save Instance</Btn>}
          </div>
        </div>}
      </div>
    </div>
    <style>{`@keyframes spin{to{transform:rotate(360deg)}} @keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}`}</style>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   MOCK DATA
   ═══════════════════════════════════════════════════════════════════════════ */
const INIT = [
  {id:"1",name:"HQ Production PBX",base_url:"https://pbx-hq.acme.com:5001",version:"20.0.3.884",status:"healthy",last_seen:"2026-02-18T10:32:00Z",credential_username:"admin",
    trunks:[{name:"Twilio US",status:"registered",provider:"Twilio",last_error:null,inbound:true,outbound:true,changed:"2026-02-17T08:00:00Z"},{name:"Vonage UK",status:"registered",provider:"Vonage",last_error:null,inbound:true,outbound:true,changed:"2026-02-16T12:30:00Z"},{name:"BT PSTN",status:"unregistered",provider:"BT",last_error:"408 Request Timeout",inbound:false,outbound:false,changed:"2026-02-18T09:45:00Z"}],
    sbcs:[{name:"SBC-East",status:"online",last_seen:"2026-02-18T10:31:00Z",tunnel:"Connected"},{name:"SBC-West",status:"online",last_seen:"2026-02-18T10:30:00Z",tunnel:"Connected"}],
    license:{edition:"Enterprise",expiry:"2026-08-15",maint:"2026-08-15",calls:64,valid:true,warnings:[]},
    backups:[{id:"b1",name:"backup_20260218_020000.zip",date:"2026-02-18T02:00:00Z",size:157286400,type:"Full"},{id:"b2",name:"backup_20260217_020000.zip",date:"2026-02-17T02:00:00Z",size:155648000,type:"Full"}],
    caps:{trunks:"available",sbcs:"available",license:"available",backup_list:"available"}},
  {id:"2",name:"Branch Office",base_url:"https://pbx-branch.acme.com:5001",version:"20.0.2.501",status:"warning",last_seen:"2026-02-18T10:30:00Z",credential_username:"monitor-svc",
    trunks:[{name:"SIP.us Trunk",status:"registered",provider:"SIP.us",last_error:null,inbound:true,outbound:true,changed:"2026-02-15T14:00:00Z"}],
    sbcs:[{name:"SBC-Branch",status:"offline",last_seen:"2026-02-18T08:15:00Z",tunnel:"Disconnected"}],
    license:{edition:"Professional",expiry:"2026-03-10",maint:"2026-03-10",calls:16,valid:true,warnings:["Expires in 20 days"]},
    backups:[{id:"b3",name:"backup_20260216.zip",date:"2026-02-16T02:00:00Z",size:52428800,type:"Full"}],
    caps:{trunks:"available",sbcs:"degraded",license:"available",backup_list:"available"}},
];
const ALERTS=[{id:"a1",sev:"critical",title:"Trunk 'BT PSTN' unregistered >60s",pbx:"HQ Production PBX",time:"2026-02-18T09:45:00Z",state:"active"},{id:"a2",sev:"critical",title:"SBC-Branch offline >2h",pbx:"Branch Office",time:"2026-02-18T08:15:00Z",state:"active"},{id:"a3",sev:"warning",title:"License expires in 20 days",pbx:"Branch Office",time:"2026-02-18T00:00:00Z",state:"active"},{id:"a4",sev:"warning",title:"No backup in 48h",pbx:"Branch Office",time:"2026-02-18T02:00:00Z",state:"active"}];
const AUDIT=[{id:"1",action:"pbx_created",user:"admin",target:"HQ Production PBX",detail:"Test connection passed, instance saved",time:"2026-02-18T07:55:00Z",ok:true},{id:"2",action:"user_login",user:"admin",target:"System",detail:"Login from 10.0.1.5",time:"2026-02-18T08:00:00Z",ok:true},{id:"3",action:"backup_downloaded",user:"admin",target:"HQ Production PBX",detail:"backup_20260218_020000.zip (150 MB)",time:"2026-02-18T08:05:00Z",ok:true},{id:"4",action:"poll_failed",user:"system",target:"Branch Office",detail:"SBC endpoint HTTP 500",time:"2026-02-18T06:00:00Z",ok:false},{id:"5",action:"capability_probe",user:"system",target:"Branch Office",detail:"SBC feature degraded — HTML fallback",time:"2026-02-17T04:00:00Z",ok:true}];

/* ═══════════════════════════════════════════════════════════════════════════
   PAGES
   ═══════════════════════════════════════════════════════════════════════════ */
function Dashboard({instances,onSelect,onAdd}){
  const tA=instances.reduce((a,i)=>a+i.trunks.length,0),tD=instances.reduce((a,i)=>a+i.trunks.filter(t=>t.status!=="registered").length,0),sO=instances.reduce((a,i)=>a+i.sbcs.filter(s=>s.status==="offline").length,0),lW=instances.reduce((a,i)=>a+(i.license.warnings?.length||0),0);
  return<div>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Dashboard</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{instances.length} instance{instances.length!==1?"s":""} monitored</p></div>
      <div style={{display:"flex",gap:8}}><Btn variant="ghost" small><Sv d={iRf} s={14}/> Refresh</Btn><Btn variant="accent" onClick={onAdd}><Sv d={iP} s={14}/> Add Instance</Btn></div>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10,marginBottom:22}}>
      {[{l:"Trunks Total",v:tA},{l:"Trunks Down",v:tD,c:tD>0?C.r:C.g},{l:"SBCs Offline",v:sO,c:sO>0?C.r:C.g},{l:"License Alerts",v:lW,c:lW>0?C.y:C.g}].map((s,i)=><Card key={i} style={{padding:14,display:"flex",justifyContent:"center"}}><Stat l={s.l} v={s.v} c={s.c}/></Card>)}
    </div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(360px,1fr))",gap:12}}>
      {instances.map(inst=>{const d=inst.trunks.filter(t=>t.status!=="registered").length,o=inst.sbcs.filter(s=>s.status==="offline").length,lb=inst.backups[0];return<Card key={inst.id} hv onClick={()=>onSelect(inst)}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:12}}><div><div style={{fontSize:15,fontWeight:600,color:C.txB}}>{inst.name}</div><div style={{fontSize:11,color:C.txM,marginTop:2,fontFamily:M}}>v{inst.version}</div></div><Pill status={inst.status}/></div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:4,padding:"12px 0",borderTop:"1px solid "+C.border}}>
          <Stat l="Trunks" v={`${inst.trunks.length-d}/${inst.trunks.length}`} c={d>0?C.r:C.g}/><Stat l="SBCs" v={`${inst.sbcs.length-o}/${inst.sbcs.length}`} c={o>0?C.r:C.g}/><Stat l="License" v={inst.license.valid?"OK":"⚠"} c={inst.license.valid?C.g:C.r}/><Stat l="Backup" v={lb?ago(lb.date):"-"} c={lb?C.txD:C.y}/>
        </div>
        <div style={{fontSize:11,color:C.txM,marginTop:6,fontFamily:M}}>{inst.base_url} · seen {ago(inst.last_seen)} ago</div>
      </Card>})}
    </div>
  </div>;
}

function Detail({inst,onBack}){const[tab,setTab]=useState("trunks");const tabs=[{id:"trunks",l:"Trunks",n:inst.trunks.length},{id:"sbcs",l:"SBCs",n:inst.sbcs.length},{id:"license",l:"License"},{id:"backups",l:"Backups",n:inst.backups.length},{id:"caps",l:"Capabilities"}];return<div>
  <Btn variant="ghost" small onClick={onBack} style={{marginBottom:8}}>← Dashboard</Btn>
  <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}><div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>{inst.name}</h1><div style={{fontSize:12,color:C.txM,marginTop:2,fontFamily:M}}>{inst.base_url} · v{inst.version} · user: {inst.credential_username}</div></div><Pill status={inst.status}/></div>
  <div style={{display:"flex",gap:0,marginBottom:16,borderBottom:"1px solid "+C.border}}>{tabs.map(t=><button key={t.id} onClick={()=>setTab(t.id)} style={{padding:"10px 18px",fontSize:13,fontWeight:tab===t.id?600:400,color:tab===t.id?C.txB:C.txM,background:"transparent",border:"none",borderBottom:tab===t.id?"2px solid "+C.ac:"2px solid transparent",cursor:"pointer",fontFamily:F}}>{t.l}{t.n!=null?` (${t.n})`:""}</button>)}</div>
  {tab==="trunks"&&<Card><Table cols={[{k:"name",l:"Trunk",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},{k:"status",l:"Status",r:v=><Pill status={v}/>},{k:"provider",l:"Provider"},{k:"last_error",l:"Last Error",r:v=>v?<span style={{color:C.r,fontSize:12,fontFamily:M}}>{v}</span>:"—"},{k:"inbound",l:"In",r:v=>v?<Sv d={iCk} s={14} c={C.g}/>:<Sv d={iX} s={14} c={C.r}/>},{k:"outbound",l:"Out",r:v=>v?<Sv d={iCk} s={14} c={C.g}/>:<Sv d={iX} s={14} c={C.r}/>},{k:"changed",l:"Changed",r:v=><span style={{fontSize:12,fontFamily:M}}>{fTime(v)}</span>}]} data={inst.trunks}/></Card>}
  {tab==="sbcs"&&<Card><Table cols={[{k:"name",l:"SBC",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},{k:"status",l:"Status",r:v=><Pill status={v}/>},{k:"tunnel",l:"Tunnel"},{k:"last_seen",l:"Last Seen",r:v=><span style={{fontSize:12,fontFamily:M}}>{fTime(v)}</span>}]} data={inst.sbcs}/></Card>}
  {tab==="license"&&<Card><div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:20,marginBottom:16}}>{[{l:"Edition",v:inst.license.edition},{l:"Expiry",v:fDate(inst.license.expiry),c:inst.license.valid?C.txB:C.r},{l:"Max Calls",v:inst.license.calls||"—"}].map((s,i)=><div key={i}><div style={{fontSize:10,color:C.txM,textTransform:"uppercase",letterSpacing:".05em",marginBottom:4}}>{s.l}</div><div style={{fontSize:18,fontWeight:600,color:s.c||C.txB,fontFamily:M}}>{s.v}</div></div>)}</div>{inst.license.warnings?.length>0&&<div style={{padding:12,background:C.yB,border:"1px solid rgba(241,196,15,.15)",borderRadius:6,marginTop:12}}>{inst.license.warnings.map((w,i)=><div key={i} style={{fontSize:13,color:C.y}}>⚠ {w}</div>)}</div>}</Card>}
  {tab==="backups"&&<Card><Table cols={[{k:"name",l:"File",r:v=><span style={{fontWeight:500,color:C.txB,fontFamily:M,fontSize:12}}>{v}</span>},{k:"date",l:"Created",r:v=>fTime(v)},{k:"size",l:"Size",r:v=>fBytes(v)},{k:"type",l:"Type"},{k:"id",l:"",r:()=><Btn small variant="primary"><Sv d={iDl} s={12}/> Download</Btn>}]} data={inst.backups}/></Card>}
  {tab==="caps"&&<Card><div style={{fontSize:12,color:C.txD,marginBottom:12}}>Discovered during connection probe — refreshed weekly</div><Table cols={[{k:"f",l:"Feature",r:v=><span style={{fontWeight:500,color:C.txB,textTransform:"capitalize"}}>{v.replace(/_/g," ")}</span>},{k:"s",l:"Status",r:v=><Pill status={v}/>}]} data={Object.entries(inst.caps).map(([f,s])=>({f,s}))}/></Card>}
</div>}

function AlertsPage(){const active=ALERTS.filter(a=>a.state==="active");return<div>
  <h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:"0 0 4px"}}>Alerts</h1><p style={{fontSize:13,color:C.txM,margin:"0 0 20px"}}>{active.length} active</p>
  <Card><Table cols={[{k:"sev",l:"Severity",r:v=><Pill status={v}/>},{k:"title",l:"Alert",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},{k:"pbx",l:"PBX"},{k:"time",l:"Triggered",r:v=>fTime(v)},{k:"id",l:"",r:()=><Btn small variant="ghost">Ack</Btn>}]} data={active}/></Card>
</div>}

function BackupsPage({instances}){const all=instances.flatMap(i=>i.backups.map(b=>({...b,pbx:i.name})));return<div>
  <h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:"0 0 4px"}}>Backups</h1><p style={{fontSize:13,color:C.txM,margin:"0 0 20px"}}>{all.length} across all instances</p>
  <Card><Table cols={[{k:"pbx",l:"PBX",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},{k:"name",l:"File",r:v=><span style={{fontFamily:M,fontSize:12}}>{v}</span>},{k:"date",l:"Created",r:v=>fTime(v)},{k:"size",l:"Size",r:v=>fBytes(v)},{k:"type",l:"Type"},{k:"id",l:"",r:()=><Btn small variant="primary"><Sv d={iDl} s={12}/> Download</Btn>}]} data={all}/></Card>
</div>}

function AuditPage(){return<div>
  <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:20}}><div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Audit Log</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{AUDIT.length} entries</p></div><Btn small>Export CSV</Btn></div>
  <Card><Table cols={[{k:"time",l:"Time",r:v=><span style={{fontSize:12,fontFamily:M}}>{fTime(v)}</span>},{k:"action",l:"Action",r:v=><span style={{fontSize:12,fontFamily:M,color:C.ac}}>{v}</span>},{k:"user",l:"User",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},{k:"target",l:"Target"},{k:"detail",l:"Detail"},{k:"ok",l:"Result",r:v=>v?<Pill status="pass" label="OK"/>:<Pill status="fail" label="FAIL"/>}]} data={AUDIT}/></Card>
</div>}

function SettingsPage(){return<div>
  <h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:"0 0 20px"}}>Settings</h1>
  <div style={{display:"grid",gap:12}}>
    <Card><div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:12}}>Security</div><div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,fontSize:13,color:C.txD}}><div><span style={{color:C.txM}}>Encryption:</span> AES-256-GCM</div><div><span style={{color:C.txM}}>Key source:</span> MASTER_KEY env var</div><div><span style={{color:C.txM}}>JWT expiry:</span> 60 min</div><div><span style={{color:C.txM}}>Login lockout:</span> 5 attempts / 15 min</div></div></Card>
    <Card><div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:12}}>Polling</div><div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,fontSize:13,color:C.txD}}><div><span style={{color:C.txM}}>Default interval:</span> 60s</div><div><span style={{color:C.txM}}>Max backoff:</span> 600s</div><div><span style={{color:C.txM}}>Alert check:</span> 30s</div><div><span style={{color:C.txM}}>Capability reprobe:</span> Weekly</div></div></Card>
    <Card><div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:12}}>Database</div><div style={{fontSize:13,color:C.txD}}><div style={{fontFamily:M,fontSize:12,color:C.txM}}>PostgreSQL 16 · Audit log: immutable (trigger-protected) · Poll history: 90-day retention</div></div></Card>
  </div>
</div>}

/* ═══════════════════════════════════════════════════════════════════════════
   APP SHELL
   ═══════════════════════════════════════════════════════════════════════════ */
export default function App(){
  const[page,setPage]=useState("dashboard");
  const[detail,setDetail]=useState(null);
  const[showAdd,setShowAdd]=useState(false);
  const[instances,setInstances]=useState(INIT);

  const nav=[
    {id:"dashboard",l:"Dashboard",d:"M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0v-4a1 1 0 011-1h2a1 1 0 011 1v4"},
    {id:"instances",l:"Instances",d:"M4 6h16M4 6a2 2 0 012-2h12a2 2 0 012 2M4 6v4a2 2 0 002 2h12a2 2 0 002-2V6M6 8h.01M6 16h.01M4 14h16v4a2 2 0 01-2 2H6a2 2 0 01-2-2v-4"},
    {id:"backups",l:"Backups",d:iDl},
    {id:"alerts",l:"Alerts",d:"M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6 6 0 00-5-5.917V4a1 1 0 10-2 0v1.083A6 6 0 006 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0a3 3 0 11-6 0"},
    {id:"audit",l:"Audit Log",d:"M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"},
    {id:"settings",l:"Settings",d:"M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z"},
  ];
  const activeAlerts=ALERTS.filter(a=>a.state==="active").length;

  const handleAddSave=(inst)=>{setInstances(p=>[...p,inst])};

  const renderPage=()=>{
    if(detail)return<Detail inst={detail} onBack={()=>setDetail(null)}/>;
    switch(page){
      case"dashboard":case"instances":return<Dashboard instances={instances} onSelect={i=>{setDetail(i);setPage("instances")}} onAdd={()=>setShowAdd(true)}/>;
      case"backups":return<BackupsPage instances={instances}/>;
      case"alerts":return<AlertsPage/>;
      case"audit":return<AuditPage/>;
      case"settings":return<SettingsPage/>;
      default:return<Dashboard instances={instances} onSelect={setDetail} onAdd={()=>setShowAdd(true)}/>;
    }
  };

  return<div style={{display:"flex",height:"100vh",background:C.bg0,color:C.tx,fontFamily:F,fontSize:14}}>
    <nav style={{width:210,background:C.bg1,borderRight:"1px solid "+C.border,display:"flex",flexDirection:"column",padding:"14px 0",flexShrink:0}}>
      <div style={{padding:"2px 18px 18px",borderBottom:"1px solid "+C.border,marginBottom:6}}>
        <div style={{fontSize:16,fontWeight:800,color:C.txB,letterSpacing:"-.02em"}}>PBXMonitor<span style={{color:C.ac}}>X</span></div>
        <div style={{fontSize:10,color:C.txM,marginTop:2,fontFamily:M}}>3CX v20 · Linux</div>
      </div>
      {nav.map(n=>{const active=(page===n.id&&!detail)||(n.id==="instances"&&detail);return<button key={n.id} onClick={()=>{setPage(n.id);setDetail(null)}} style={{display:"flex",alignItems:"center",gap:10,padding:"9px 18px",margin:"1px 8px",borderRadius:6,border:"none",cursor:"pointer",fontFamily:F,fontSize:13,fontWeight:active?600:400,color:active?C.txB:C.txD,background:active?C.acBg:"transparent",transition:"all .12s",textAlign:"left",position:"relative"}}>
        <Sv d={n.d} s={16} c={active?C.ac:C.txD}/>{n.l}
        {n.id==="alerts"&&activeAlerts>0&&<span style={{position:"absolute",right:12,background:C.r,color:"#fff",fontSize:9,fontWeight:700,padding:"1px 5px",borderRadius:99,minWidth:16,textAlign:"center"}}>{activeAlerts}</span>}
      </button>})}
      <div style={{flex:1}}/>
      <div style={{padding:"10px 18px",borderTop:"1px solid "+C.border,fontSize:10,color:C.txM,fontFamily:M}}>v0.1.0 · <span style={{color:C.g}}>●</span> Connected</div>
    </nav>
    <main style={{flex:1,overflow:"auto",padding:"24px 32px"}}>{renderPage()}</main>
    {showAdd&&<AddInstanceModal onClose={()=>setShowAdd(false)} onSave={handleAddSave}/>}
    <style>{`
      @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700;800&display=swap');
      @keyframes spin{to{transform:rotate(360deg)}}
      @keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
      *{box-sizing:border-box;margin:0;padding:0}
      ::-webkit-scrollbar{width:6px;height:6px}
      ::-webkit-scrollbar-track{background:${C.bg0}}
      ::-webkit-scrollbar-thumb{background:${C.border};border-radius:3px}
      ::-webkit-scrollbar-thumb:hover{background:${C.borderL}}
      input::placeholder{color:${C.txM}}
    `}</style>
  </div>;
}
