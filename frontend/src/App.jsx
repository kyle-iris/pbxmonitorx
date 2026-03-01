import { useState, useEffect, useCallback, useRef } from "react";

/* ═══════════════════════════════════════════════════════════════════════════
   THEME + UTILS
   ═══════════════════════════════════════════════════════════════════════════ */
const C = { bg0:"#0A0A08",bg1:"#111110",bg2:"#1A1918",bg3:"#222120",border:"#2C2A28",borderL:"#3A3836",tx:"#D4D0CB",txD:"#8A8580",txM:"#5E5A55",txB:"#EDE9E4",ac:"#C8965A",acD:"#A0784A",acBg:"rgba(200,150,90,.08)",g:"#2ECC71",gB:"rgba(46,204,113,.1)",y:"#F1C40F",yB:"rgba(241,196,15,.1)",r:"#E74C3C",rB:"rgba(231,76,60,.1)",b:"#3498DB",bB:"rgba(52,152,219,.1)" };
const F = `"IBM Plex Sans",system-ui,sans-serif`, M = `"IBM Plex Mono","Consolas",monospace`;

const ago=(iso)=>{if(!iso)return"—";const m=Math.floor((Date.now()-new Date(iso))/60000);if(m<1)return"now";if(m<60)return m+"m";const h=Math.floor(m/60);return h<24?h+"h":Math.floor(h/24)+"d"};
const fDate=(iso)=>iso?new Date(iso).toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"}):"—";
const fTime=(iso)=>iso?new Date(iso).toLocaleString("en-US",{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"}):"—";
const fBytes=(b)=>{if(!b&&b!==0)return"—";if(b>1e9)return(b/1e9).toFixed(1)+" GB";if(b>1e6)return(b/1e6).toFixed(0)+" MB";return(b/1024).toFixed(0)+" KB"};
const sc=(s)=>({healthy:C.g,registered:C.g,online:C.g,available:C.g,pass:C.g,warning:C.y,degraded:C.y,warn:C.y,no_schedule:C.y,error:C.r,unregistered:C.r,offline:C.r,unavailable:C.r,critical:C.r,fail:C.r,stale:C.r,no_backups:C.r,info:C.b,skip:C.txM,untested:C.txM}[s]||C.txM);
const sbg=(s)=>({healthy:C.gB,registered:C.gB,online:C.gB,available:C.gB,pass:C.gB,warning:C.yB,degraded:C.yB,warn:C.yB,no_schedule:C.yB,error:C.rB,unregistered:C.rB,offline:C.rB,unavailable:C.rB,critical:C.rB,fail:C.rB,stale:C.rB,no_backups:C.rB,info:C.bB}[s]||"rgba(94,90,85,.06)");

/* ═══════════════════════════════════════════════════════════════════════════
   API CLIENT
   ═══════════════════════════════════════════════════════════════════════════ */
const API = "/api";
const headers = () => ({ "Content-Type":"application/json",...(localStorage.getItem("token")?{Authorization:`Bearer ${localStorage.getItem("token")}`}:{})});
const api = {
  get: (p) => fetch(API+p,{headers:headers()}).then(r=>{if(r.status===401){localStorage.removeItem("token");localStorage.removeItem("user");window.dispatchEvent(new Event("auth-change"));return Promise.reject(r)}return r.ok?r.json():Promise.reject(r)}),
  post: (p,b) => fetch(API+p,{method:"POST",headers:headers(),body:JSON.stringify(b)}).then(r=>{if(r.status===401){localStorage.removeItem("token");localStorage.removeItem("user");window.dispatchEvent(new Event("auth-change"));return Promise.reject(r)}return r.ok?r.json():Promise.reject(r)}),
  patch: (p,b) => fetch(API+p,{method:"PATCH",headers:headers(),body:JSON.stringify(b)}).then(r=>r.ok?r.json():Promise.reject(r)),
  put: (p,b) => fetch(API+p,{method:"PUT",headers:headers(),body:JSON.stringify(b)}).then(r=>r.ok?r.json():Promise.reject(r)),
  del: (p) => fetch(API+p,{method:"DELETE",headers:headers()}).then(r=>r.ok?r.json():Promise.reject(r)),
};

/* ═══════════════════════════════════════════════════════════════════════════
   COMPONENTS
   ═══════════════════════════════════════════════════════════════════════════ */
const iCk="M5 13l4 4L19 7",iX="M6 18L18 6M6 6l12 12",iDl="M12 4v12m0 0l-4-4m4 4l4-4M4 18h16",iRf="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15",iP="M12 4v16m8-8H4",iLk="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z",iSh="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",iW="M12 9v2m0 4h.01M5.07 19h13.86c1.54 0 2.5-1.67 1.73-3L13.73 4c-.77-1.33-2.69-1.33-3.46 0L3.34 16c-.77 1.33.19 3 1.73 3z",iEye="M15 12a3 3 0 11-6 0 3 3 0 016 0zM2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z",iEyeX="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M3 3l18 18",iUser="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z",iPhone="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z",iLogout="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1";

const Pill=({status,label})=><span style={{display:"inline-flex",alignItems:"center",gap:5,padding:"2px 10px",borderRadius:99,fontSize:11,fontWeight:600,letterSpacing:".04em",textTransform:"uppercase",color:sc(status),background:sbg(status),whiteSpace:"nowrap"}}><span style={{width:6,height:6,borderRadius:"50%",background:sc(status)}}/>{label||status}</span>;
const Stat=({l,v,c})=><div style={{textAlign:"center"}}><div style={{fontSize:20,fontWeight:700,color:c||C.txB,fontFamily:M}}>{v}</div><div style={{fontSize:9,color:C.txM,textTransform:"uppercase",letterSpacing:".06em",marginTop:3,fontWeight:600}}>{l}</div></div>;
const Sv=({d,s=18,c="currentColor"})=><svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={d}/></svg>;
const Spin=({s=20})=><span style={{display:"inline-block",width:s,height:s,border:"2px solid "+C.border,borderTopColor:C.ac,borderRadius:"50%",animation:"spin .6s linear infinite"}}/>;
const Toast=({msg,type="info",onClose})=><div style={{position:"fixed",top:20,right:20,zIndex:2000,padding:"12px 20px",background:type==="error"?C.rB:type==="success"?C.gB:C.bB,border:"1px solid "+(type==="error"?"rgba(231,76,60,.3)":type==="success"?"rgba(46,204,113,.3)":"rgba(52,152,219,.3)"),borderRadius:8,color:type==="error"?C.r:type==="success"?C.g:C.b,fontSize:13,fontWeight:500,cursor:"pointer",maxWidth:400}} onClick={onClose}>{msg}</div>;

function Btn({children,variant="default",onClick,small,disabled,loading,style:sx,type}){const[h,setH]=useState(false);const v={default:{bg:C.bg3,bh:"#2E2C2A",bc:C.borderL,c:C.tx},primary:{bg:"#1B6B3A",bh:"#1E8045",bc:"#1B6B3A",c:"#fff"},danger:{bg:"#6B1A1A",bh:"#801F1F",bc:"#6B1A1A",c:"#FCA5A5"},ghost:{bg:"transparent",bh:"rgba(255,255,255,.04)",bc:"transparent",c:C.txD},accent:{bg:C.acD,bh:C.ac,bc:C.acD,c:"#fff"}}[variant];return<button type={type||"button"} onClick={onClick} disabled={disabled||loading} onMouseEnter={()=>setH(true)} onMouseLeave={()=>setH(false)} style={{display:"inline-flex",alignItems:"center",justifyContent:"center",gap:6,padding:small?"5px 12px":"9px 18px",fontSize:small?12:13,fontWeight:600,background:disabled?C.bg2:h?v.bh:v.bg,border:"1px solid "+(disabled?C.border:v.bc),borderRadius:6,color:disabled?C.txM:v.c,cursor:disabled?"not-allowed":"pointer",transition:"all .12s",fontFamily:F,opacity:disabled?.5:1,...sx}}>{loading&&<Spin s={14}/>}{children}</button>}

function Card({children,style,onClick,hv}){const[h,setH]=useState(false);return<div onClick={onClick} onMouseEnter={()=>setH(true)} onMouseLeave={()=>setH(false)} style={{background:h&&hv?C.bg3:C.bg2,border:"1px solid "+C.border,borderRadius:8,padding:20,cursor:onClick?"pointer":"default",transition:"all .15s",transform:h&&hv?"translateY(-1px)":"none",boxShadow:h&&hv?"0 6px 24px rgba(0,0,0,.4)":"none",...style}}>{children}</div>}

function Table({cols,data}){return<div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}><thead><tr>{cols.map(c=><th key={c.k} style={{textAlign:"left",padding:"10px 14px",borderBottom:"1px solid "+C.border,fontSize:10,textTransform:"uppercase",letterSpacing:".06em",color:C.txM,fontWeight:700}}>{c.l}</th>)}</tr></thead><tbody>{data.map((r,i)=><tr key={r.id||i} style={{borderBottom:"1px solid rgba(44,42,40,.4)"}}>{cols.map(c=><td key={c.k} style={{padding:"10px 14px",color:C.tx}}>{c.r?c.r(r[c.k],r):(r[c.k]||"—")}</td>)}</tr>)}{data.length===0&&<tr><td colSpan={cols.length} style={{padding:40,textAlign:"center",color:C.txM}}>No data</td></tr>}</tbody></table></div>}

function Input({label,value,onChange,type="text",placeholder,help,error,mono,required,icon}){const[show,setShow]=useState(false);const isPass=type==="password";return<div style={{marginBottom:16}}><label style={{display:"block",fontSize:11,fontWeight:600,color:C.txD,textTransform:"uppercase",letterSpacing:".05em",marginBottom:5}}>{label}{required&&<span style={{color:C.r}}>*</span>}</label><div style={{position:"relative"}}><input type={isPass&&show?"text":type} value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder} style={{width:"100%",padding:"9px 12px",paddingRight:isPass?36:12,fontSize:13,fontFamily:mono?M:F,background:C.bg1,border:"1px solid "+(error?C.r:C.border),borderRadius:6,color:C.txB,outline:"none",boxSizing:"border-box",transition:"border-color .15s"}} onFocus={e=>e.target.style.borderColor=C.ac} onBlur={e=>e.target.style.borderColor=error?C.r:C.border}/>{isPass&&<button type="button" onClick={()=>setShow(!show)} style={{position:"absolute",right:8,top:"50%",transform:"translateY(-50%)",background:"none",border:"none",cursor:"pointer",padding:2}}><Sv d={show?iEyeX:iEye} s={16} c={C.txM}/></button>}</div>{help&&!error&&<div style={{fontSize:11,color:C.txM,marginTop:3}}>{help}</div>}{error&&<div style={{fontSize:11,color:C.r,marginTop:3}}>{error}</div>}</div>}

function Select({label,value,onChange,options,help}){return<div style={{marginBottom:16}}><label style={{display:"block",fontSize:11,fontWeight:600,color:C.txD,textTransform:"uppercase",letterSpacing:".05em",marginBottom:5}}>{label}</label><select value={value} onChange={e=>onChange(e.target.value)} style={{width:"100%",padding:"9px 12px",fontSize:13,fontFamily:F,background:C.bg1,border:"1px solid "+C.border,borderRadius:6,color:C.txB,outline:"none",cursor:"pointer"}}>{options.map(o=><option key={o.v} value={o.v}>{o.l}</option>)}</select>{help&&<div style={{fontSize:11,color:C.txM,marginTop:3}}>{help}</div>}</div>}

/* ═══════════════════════════════════════════════════════════════════════════
   LOGIN PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function LoginPage({onLogin}){
  const[username,setUsername]=useState("");
  const[password,setPassword]=useState("");
  const[error,setError]=useState("");
  const[loading,setLoading]=useState(false);
  const[ssoEnabled,setSsoEnabled]=useState(false);

  useEffect(()=>{api.get("/auth/sso/config").then(r=>{if(r.sso_enabled)setSsoEnabled(true)}).catch(()=>{})},[]);

  const handleLogin=async(e)=>{
    e.preventDefault(); setError(""); setLoading(true);
    try{
      const r=await api.post("/auth/login",{username,password});
      localStorage.setItem("token",r.access_token);
      localStorage.setItem("user",JSON.stringify(r.user||{username,role:"viewer"}));
      onLogin();
    }catch(err){
      setError("Invalid username or password");
    }finally{setLoading(false)}
  };

  return<div style={{display:"flex",alignItems:"center",justifyContent:"center",height:"100vh",background:C.bg0}}>
    <div style={{width:380,padding:40,background:C.bg1,border:"1px solid "+C.border,borderRadius:12}}>
      <div style={{textAlign:"center",marginBottom:30}}>
        <div style={{fontSize:28,fontWeight:800,color:C.txB}}>PBXMonitor<span style={{color:C.ac}}>X</span></div>
        <div style={{fontSize:12,color:C.txM,marginTop:4,fontFamily:M}}>3CX v20 Monitor & Backup</div>
      </div>
      <form onSubmit={handleLogin}>
        <Input label="Username" value={username} onChange={setUsername} placeholder="admin" required/>
        <Input label="Password" value={password} onChange={setPassword} type="password" placeholder="••••••••" required/>
        {error&&<div style={{color:C.r,fontSize:12,marginBottom:12}}>{error}</div>}
        <Btn variant="accent" type="submit" loading={loading} style={{width:"100%",marginBottom:12}}>Sign In</Btn>
      </form>
      {ssoEnabled&&<>
        <div style={{display:"flex",alignItems:"center",gap:12,margin:"16px 0"}}><div style={{flex:1,height:1,background:C.border}}/><span style={{fontSize:11,color:C.txM}}>OR</span><div style={{flex:1,height:1,background:C.border}}/></div>
        <Btn variant="default" onClick={()=>{window.location.href=API+"/auth/sso/login"}} style={{width:"100%"}}><Sv d="M6 6h5v5H6V6zm7 0h5v5h-5V6zm-7 7h5v5H6v-5zm7 7h5v-5h-5v5z" s={16} c={C.b}/> Sign in with Microsoft</Btn>
      </>}
    </div>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   ADD INSTANCE MODAL
   ═══════════════════════════════════════════════════════════════════════════ */
function AddInstanceModal({onClose,onSave}){
  const[step,setStep]=useState("form");
  const[form,setForm]=useState({name:"",base_url:"https://",username:"admin",password:"",tls_policy:"verify",poll_interval_s:60,notes:""});
  const[errors,setErrors]=useState({});
  const[testResult,setTestResult]=useState(null);
  const[testSteps,setTestSteps]=useState([]);
  const[saving,setSaving]=useState(false);
  const upd=(k,v)=>setForm(p=>({...p,[k]:v}));

  const validate=()=>{const e={};if(!form.name.trim()||form.name.length<2)e.name="Name must be at least 2 characters";if(!form.base_url.startsWith("https://"))e.base_url="Must start with https://";if(form.base_url.length<10)e.base_url="Enter a valid URL";if(!form.username.trim())e.username="Required";if(!form.password)e.password="Required";setErrors(e);return Object.keys(e).length===0};

  const runTest=async()=>{
    if(!validate())return;
    setStep("testing");setTestSteps([]);setTestResult(null);
    try{
      const r=await api.post("/pbx/test-connection",{base_url:form.base_url,username:form.username,password:form.password,tls_policy:form.tls_policy});
      if(r.steps)setTestSteps(r.steps);
      setTestResult(r);
    }catch(err){
      setTestResult({success:false,message:"Connection test failed. Check the URL and credentials."});
    }
    setStep("results");
  };

  const saveInstance=async()=>{
    setSaving(true);
    try{
      const r=await api.post("/pbx/instances",{name:form.name,base_url:form.base_url,username:form.username,password:form.password,tls_policy:form.tls_policy,poll_interval_s:form.poll_interval_s,notes:form.notes,capabilities:testResult?.capabilities||[]});
      onSave(r);onClose();
    }catch(err){alert("Failed to save instance")}
    setSaving(false);
  };

  return<div style={{position:"fixed",inset:0,zIndex:1000,display:"flex",alignItems:"center",justifyContent:"center"}}>
    <div style={{position:"absolute",inset:0,background:"rgba(0,0,0,.7)",backdropFilter:"blur(4px)"}} onClick={onClose}/>
    <div style={{position:"relative",background:C.bg1,border:"1px solid "+C.border,borderRadius:12,width:560,maxHeight:"90vh",overflow:"auto",boxShadow:"0 20px 60px rgba(0,0,0,.6)"}}>
      <div style={{padding:"20px 24px",borderBottom:"1px solid "+C.border,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
        <div><div style={{fontSize:17,fontWeight:700,color:C.txB}}>Add PBX System</div><div style={{fontSize:12,color:C.txM,marginTop:2}}>{step==="form"?"Enter connection details":step==="testing"?"Testing connectivity…":"Connection "+(testResult?.success?"verified":"failed")}</div></div>
        <button onClick={onClose} style={{background:"none",border:"none",cursor:"pointer",padding:4}}><Sv d={iX} s={20} c={C.txM}/></button>
      </div>
      <div style={{padding:"20px 24px"}}>
        {step==="form"&&<>
          <div style={{display:"flex",gap:10,padding:12,background:C.acBg,border:"1px solid rgba(200,150,90,.15)",borderRadius:6,marginBottom:20,fontSize:12,color:C.ac}}><Sv d={iSh} s={18} c={C.ac}/><div><strong>Credentials encrypted at rest</strong> with AES-256-GCM.</div></div>
          <Input label="System Name" value={form.name} onChange={v=>upd("name",v)} placeholder="e.g. HQ Production PBX" error={errors.name} required/>
          <Input label="PBX URL" value={form.base_url} onChange={v=>upd("base_url",v)} placeholder="https://pbx.example.com:5001" help="Full HTTPS URL to the 3CX management console" error={errors.base_url} mono required/>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}><Input label="Admin Username" value={form.username} onChange={v=>upd("username",v)} error={errors.username} required/><Input label="Password" value={form.password} onChange={v=>upd("password",v)} type="password" error={errors.password} required/></div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
            <Select label="TLS Verification" value={form.tls_policy} onChange={v=>upd("tls_policy",v)} options={[{v:"verify",l:"Verify Certificate"},{v:"trust_self_signed",l:"Trust Self-Signed"}]}/>
            <Select label="Poll Interval" value={form.poll_interval_s} onChange={v=>upd("poll_interval_s",+v)} options={[{v:30,l:"30 seconds"},{v:60,l:"60 seconds"},{v:300,l:"5 minutes"},{v:600,l:"10 minutes"}]}/>
          </div>
          <Input label="Notes" value={form.notes} onChange={v=>upd("notes",v)} placeholder="Optional description…"/>
          <div style={{display:"flex",justifyContent:"flex-end",gap:10,paddingTop:8,borderTop:"1px solid "+C.border}}><Btn variant="ghost" onClick={onClose}>Cancel</Btn><Btn variant="accent" onClick={runTest}><Sv d={iSh} s={14}/> Test Connection</Btn></div>
        </>}
        {step==="testing"&&<div style={{textAlign:"center",padding:40}}><Spin s={32}/><div style={{color:C.txD,marginTop:16}}>Testing connectivity…</div></div>}
        {step==="results"&&<div>
          <div style={{display:"flex",gap:12,padding:14,background:testResult.success?C.gB:C.rB,border:"1px solid "+(testResult.success?"rgba(46,204,113,.2)":"rgba(231,76,60,.2)"),borderRadius:8,marginBottom:18}}>
            <div>{testResult.success?<Sv d={iCk} s={22} c={C.g}/>:<Sv d={iX} s={22} c={C.r}/>}</div>
            <div><div style={{fontSize:15,fontWeight:700,color:testResult.success?C.g:C.r}}>{testResult.success?"Connection Successful":"Connection Failed"}</div><div style={{fontSize:12,color:C.txD,marginTop:2}}>{testResult.message}</div>{testResult.version&&<div style={{fontSize:11,color:C.txM,marginTop:2,fontFamily:M}}>3CX Version: {testResult.version}</div>}</div>
          </div>
          {testResult.capabilities?.length>0&&<div style={{marginBottom:18}}><div style={{fontSize:11,fontWeight:700,color:C.txM,textTransform:"uppercase",letterSpacing:".05em",marginBottom:8}}>Capability Matrix</div><div style={{display:"grid",gridTemplateColumns:"repeat(2,1fr)",gap:6}}>{testResult.capabilities.map((c,i)=><div key={i} style={{display:"flex",alignItems:"center",gap:8,padding:"8px 12px",background:C.bg0,borderRadius:6,border:"1px solid "+C.border}}><span style={{width:8,height:8,borderRadius:"50%",background:sc(c.status)}}/><span style={{fontSize:12,fontWeight:500,color:C.txB,textTransform:"capitalize"}}>{c.feature.replace(/_/g," ")}</span></div>)}</div></div>}
          {testSteps?.length>0&&<details style={{marginBottom:18}}><summary style={{fontSize:11,fontWeight:600,color:C.txM,cursor:"pointer",textTransform:"uppercase",letterSpacing:".05em"}}>Connection Steps ({testSteps.length})</summary><div style={{marginTop:8}}>{testSteps.map((s,i)=><div key={i} style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0",fontSize:12}}><span style={{width:6,height:6,borderRadius:"50%",background:sc(s.status)}}/><span style={{color:C.txD,fontFamily:M}}>{s.message}</span></div>)}</div></details>}
          <div style={{display:"flex",justifyContent:"flex-end",gap:10,paddingTop:12,borderTop:"1px solid "+C.border}}>
            <Btn variant="ghost" onClick={()=>{setStep("form");setTestResult(null)}}>← Edit</Btn>
            {!testResult.success&&<Btn variant="accent" onClick={runTest}><Sv d={iRf} s={14}/> Retry</Btn>}
            {testResult.success&&<Btn variant="primary" onClick={saveInstance} loading={saving}><Sv d={iCk} s={14}/> Save System</Btn>}
          </div>
        </div>}
      </div>
    </div>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   MODAL (generic)
   ═══════════════════════════════════════════════════════════════════════════ */
function Modal({title,onClose,children,width=480}){
  return<div style={{position:"fixed",inset:0,zIndex:1000,display:"flex",alignItems:"center",justifyContent:"center"}}>
    <div style={{position:"absolute",inset:0,background:"rgba(0,0,0,.7)"}} onClick={onClose}/>
    <div style={{position:"relative",background:C.bg1,border:"1px solid "+C.border,borderRadius:12,width,maxHeight:"90vh",overflow:"auto",boxShadow:"0 20px 60px rgba(0,0,0,.6)"}}>
      <div style={{padding:"16px 24px",borderBottom:"1px solid "+C.border,display:"flex",justifyContent:"space-between",alignItems:"center"}}><div style={{fontSize:16,fontWeight:700,color:C.txB}}>{title}</div><button onClick={onClose} style={{background:"none",border:"none",cursor:"pointer"}}><Sv d={iX} s={18} c={C.txM}/></button></div>
      <div style={{padding:"20px 24px"}}>{children}</div>
    </div>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   DASHBOARD PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function DashboardPage({onSelectSystem,onAdd}){
  const[instances,setInstances]=useState([]);
  const[alerts,setAlerts]=useState([]);
  const[backupStatus,setBackupStatus]=useState(null);
  const[phoneSummary,setPhoneSummary]=useState(null);
  const[loading,setLoading]=useState(true);

  const load=useCallback(()=>{
    Promise.all([
      api.get("/pbx/instances").catch(()=>[]),
      api.get("/alerts?state=firing").catch(()=>({events:[]})),
      api.get("/backups/status").catch(()=>null),
      api.get("/phone-numbers/summary").catch(()=>null),
    ]).then(([inst,al,bs,ps])=>{
      setInstances(Array.isArray(inst)?inst:inst.instances||[]);
      setAlerts(Array.isArray(al)?al:al.events||[]);
      setBackupStatus(bs);
      setPhoneSummary(ps);
      setLoading(false);
    });
  },[]);

  useEffect(()=>{load();const iv=setInterval(load,30000);return()=>clearInterval(iv)},[load]);

  if(loading)return<div style={{textAlign:"center",padding:80}}><Spin s={32}/></div>;

  const firingAlerts=alerts.filter(a=>a.state==="firing");
  const healthySystems=instances.filter(i=>!i.last_error&&i.is_enabled).length;
  const backupHealth=backupStatus?backupStatus.per_pbx?.filter(p=>p.health==="healthy").length+"/"+backupStatus.total_pbx_count:"—";

  return<div>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Dashboard</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{instances.length} system{instances.length!==1?"s":""} monitored</p></div>
      <div style={{display:"flex",gap:8}}><Btn variant="ghost" small onClick={load}><Sv d={iRf} s={14}/> Refresh</Btn><Btn variant="accent" onClick={onAdd}><Sv d={iP} s={14}/> Add System</Btn></div>
    </div>
    {/* Stats row */}
    <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10,marginBottom:22}}>
      <Card style={{padding:14,display:"flex",justifyContent:"center"}}><Stat l="PBX Systems" v={instances.length} c={healthySystems===instances.length?C.g:C.y}/></Card>
      <Card style={{padding:14,display:"flex",justifyContent:"center"}}><Stat l="Active Alerts" v={firingAlerts.length} c={firingAlerts.length>0?C.r:C.g}/></Card>
      <Card style={{padding:14,display:"flex",justifyContent:"center"}}><Stat l="Backup Health" v={backupHealth} c={C.txB}/></Card>
      <Card style={{padding:14,display:"flex",justifyContent:"center"}}><Stat l="Phone Numbers" v={phoneSummary?.total||0} c={C.b}/></Card>
    </div>
    {/* System cards */}
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(340px,1fr))",gap:12,marginBottom:22}}>
      {instances.map(inst=><Card key={inst.id} hv onClick={()=>onSelectSystem(inst)}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:10}}>
          <div><div style={{fontSize:15,fontWeight:600,color:C.txB}}>{inst.name}</div><div style={{fontSize:11,color:C.txM,fontFamily:M}}>{inst.detected_version?"v"+inst.detected_version:inst.base_url}</div></div>
          <Pill status={inst.last_error?"error":inst.is_enabled?"healthy":"offline"}/>
        </div>
        <div style={{fontSize:11,color:C.txM,fontFamily:M}}>{inst.base_url} · polled {ago(inst.last_poll_at)}</div>
        {inst.last_error&&<div style={{fontSize:11,color:C.r,marginTop:4}}>{inst.last_error}</div>}
      </Card>)}
      {instances.length===0&&<Card style={{padding:40,textAlign:"center"}}><div style={{color:C.txM,marginBottom:12}}>No PBX systems configured yet</div><Btn variant="accent" onClick={onAdd}><Sv d={iP} s={14}/> Add Your First System</Btn></Card>}
    </div>
    {/* Backup status table */}
    {backupStatus?.per_pbx?.length>0&&<div style={{marginBottom:22}}>
      <h2 style={{fontSize:16,fontWeight:600,color:C.txB,marginBottom:10}}>Backup Status</h2>
      <Card><Table cols={[
        {k:"pbx_name",l:"System",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},
        {k:"health",l:"Health",r:v=><Pill status={v}/>},
        {k:"latest_backup",l:"Last Backup",r:(v)=>v?fTime(v.downloaded_at):"Never"},
        {k:"backup_count",l:"Total"},
        {k:"total_size_bytes",l:"Size",r:v=>fBytes(v)},
        {k:"schedule",l:"Schedule",r:v=>v?v.is_enabled?v.cron_expr:"Disabled":"None"},
      ]} data={backupStatus.per_pbx}/></Card>
    </div>}
    {/* Recent alerts */}
    {firingAlerts.length>0&&<div>
      <h2 style={{fontSize:16,fontWeight:600,color:C.txB,marginBottom:10}}>Active Alerts</h2>
      <Card><Table cols={[
        {k:"severity",l:"Severity",r:v=><Pill status={v}/>},
        {k:"title",l:"Alert",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},
        {k:"fired_at",l:"Triggered",r:v=>fTime(v)},
      ]} data={firingAlerts.slice(0,5)}/></Card>
    </div>}
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   SYSTEMS PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function SystemsPage({onAdd}){
  const[instances,setInstances]=useState([]);
  const[selected,setSelected]=useState(null);
  const[status,setStatus]=useState(null);
  const[loading,setLoading]=useState(true);
  const[polling,setPolling]=useState(false);

  const load=()=>{api.get("/pbx/instances").then(d=>{setInstances(Array.isArray(d)?d:d.instances||[]);setLoading(false)}).catch(()=>setLoading(false))};
  useEffect(()=>{load()},[]);

  const loadStatus=(id)=>{api.get("/pbx/instances/"+id+"/status").then(setStatus).catch(()=>{})};
  const selectSystem=(inst)=>{setSelected(inst);loadStatus(inst.id)};
  const pollNow=()=>{if(!selected)return;setPolling(true);api.post("/pbx/instances/"+selected.id+"/poll").then(()=>{setTimeout(()=>{loadStatus(selected.id);setPolling(false)},3000)}).catch(()=>setPolling(false))};
  const deleteSystem=(id)=>{if(confirm("Delete this system?"))api.del("/pbx/instances/"+id).then(()=>{setSelected(null);load()})};

  if(loading)return<div style={{textAlign:"center",padding:80}}><Spin/></div>;

  if(selected){
    const s=status||{};
    const trunks=s.trunks||[];const sbcs=s.sbcs||[];const license=s.license||{};const caps=s.capabilities||[];
    return<div>
      <Btn variant="ghost" small onClick={()=>{setSelected(null);setStatus(null)}} style={{marginBottom:8}}>← All Systems</Btn>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}>
        <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>{selected.name}</h1><div style={{fontSize:12,color:C.txM,fontFamily:M}}>{selected.base_url}{selected.detected_version?" · v"+selected.detected_version:""}</div></div>
        <div style={{display:"flex",gap:8}}><Btn small onClick={pollNow} loading={polling}><Sv d={iRf} s={14}/> Poll Now</Btn><Btn variant="danger" small onClick={()=>deleteSystem(selected.id)}>Delete</Btn></div>
      </div>
      {/* Trunks */}
      <h3 style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:8}}>Trunks ({trunks.length})</h3>
      <Card style={{marginBottom:16}}><Table cols={[{k:"trunk_name",l:"Name",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},{k:"status",l:"Status",r:v=><Pill status={v}/>},{k:"provider",l:"Provider"},{k:"last_error",l:"Error",r:v=>v?<span style={{color:C.r,fontSize:12,fontFamily:M}}>{v}</span>:"—"},{k:"inbound_enabled",l:"In",r:v=>v===true?<Sv d={iCk} s={14} c={C.g}/>:v===false?<Sv d={iX} s={14} c={C.r}/>:"—"},{k:"outbound_enabled",l:"Out",r:v=>v===true?<Sv d={iCk} s={14} c={C.g}/>:v===false?<Sv d={iX} s={14} c={C.r}/>:"—"}]} data={trunks}/></Card>
      {/* SBCs */}
      <h3 style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:8}}>SBCs ({sbcs.length})</h3>
      <Card style={{marginBottom:16}}><Table cols={[{k:"sbc_name",l:"Name",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},{k:"status",l:"Status",r:v=><Pill status={v}/>},{k:"tunnel_status",l:"Tunnel"},{k:"last_seen",l:"Last Seen",r:v=>fTime(v)}]} data={sbcs}/></Card>
      {/* License */}
      {license.edition&&<><h3 style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:8}}>License</h3>
      <Card style={{marginBottom:16}}><div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:16}}>{[{l:"Edition",v:license.edition},{l:"Expiry",v:fDate(license.expiry_date)},{l:"Max Calls",v:license.max_sim_calls||"—"},{l:"Valid",v:license.is_valid?"Yes":"No",c:license.is_valid?C.g:C.r}].map((s,i)=><div key={i}><div style={{fontSize:10,color:C.txM,textTransform:"uppercase",marginBottom:4}}>{s.l}</div><div style={{fontSize:16,fontWeight:600,color:s.c||C.txB,fontFamily:M}}>{s.v}</div></div>)}</div>{license.warnings?.length>0&&<div style={{padding:10,background:C.yB,borderRadius:6,marginTop:12}}>{license.warnings.map((w,i)=><div key={i} style={{fontSize:12,color:C.y}}>⚠ {w}</div>)}</div>}</Card></>}
      {/* Capabilities */}
      {caps.length>0&&<><h3 style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:8}}>Capabilities</h3>
      <Card><div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:6}}>{caps.map((c,i)=><div key={i} style={{display:"flex",alignItems:"center",gap:8,padding:"8px 12px",background:C.bg0,borderRadius:6,border:"1px solid "+C.border}}><span style={{width:8,height:8,borderRadius:"50%",background:sc(c.status)}}/><span style={{fontSize:12,color:C.txB,textTransform:"capitalize"}}>{c.feature.replace(/_/g," ")}</span><span style={{flex:1}}/><span style={{fontSize:10,color:C.txM,fontFamily:M}}>{c.status}</span></div>)}</div></Card></>}
    </div>;
  }

  return<div>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Systems</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{instances.length} configured</p></div>
      <Btn variant="accent" onClick={onAdd}><Sv d={iP} s={14}/> Add System</Btn>
    </div>
    <Card><Table cols={[
      {k:"name",l:"Name",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},
      {k:"base_url",l:"URL",r:v=><span style={{fontFamily:M,fontSize:12}}>{v}</span>},
      {k:"detected_version",l:"Version",r:v=>v||"—"},
      {k:"is_enabled",l:"Status",r:(v,r)=><Pill status={r.last_error?"error":v?"healthy":"offline"}/>},
      {k:"last_poll_at",l:"Last Poll",r:v=>fTime(v)},
      {k:"poll_interval_s",l:"Interval",r:v=>v?v+"s":"—"},
      {k:"id",l:"",r:(_,r)=><Btn small onClick={(e)=>{e.stopPropagation();selectSystem(r)}}>View</Btn>},
    ]} data={instances}/></Card>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   PHONE NUMBERS PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function PhoneNumbersPage(){
  const[numbers,setNumbers]=useState([]);
  const[total,setTotal]=useState(0);
  const[summary,setSummary]=useState(null);
  const[search,setSearch]=useState("");
  const[pbxFilter,setPbxFilter]=useState("");
  const[typeFilter,setTypeFilter]=useState("");
  const[syncing,setSyncing]=useState(false);
  const[loading,setLoading]=useState(true);
  const[toast,setToast]=useState(null);

  const load=useCallback(()=>{
    const params=new URLSearchParams();
    if(search)params.set("search",search);
    if(pbxFilter)params.set("pbx_id",pbxFilter);
    if(typeFilter)params.set("number_type",typeFilter);
    params.set("limit","200");
    Promise.all([
      api.get("/phone-numbers?"+params).catch(()=>({entries:[],total:0})),
      api.get("/phone-numbers/summary").catch(()=>null),
    ]).then(([d,s])=>{
      setNumbers(d.entries||[]);setTotal(d.total||0);setSummary(s);setLoading(false);
    });
  },[search,pbxFilter,typeFilter]);

  useEffect(()=>{load()},[load]);

  const syncAll=async()=>{setSyncing(true);try{const r=await api.post("/phone-numbers/sync-all");setToast({msg:r.message||"Sync complete",type:"success"});load()}catch(e){setToast({msg:"Sync failed",type:"error"})}setSyncing(false)};

  if(loading)return<div style={{textAlign:"center",padding:80}}><Spin/></div>;

  return<div>
    {toast&&<Toast {...toast} onClose={()=>setToast(null)}/>}
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Phone Numbers</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{total} numbers across all systems</p></div>
      <div style={{display:"flex",gap:8}}>
        <Btn small variant="ghost" onClick={()=>window.open(API+"/phone-numbers/export"+(pbxFilter?"?pbx_id="+pbxFilter:""))}><Sv d={iDl} s={14}/> Export CSV</Btn>
        <Btn small variant="primary" onClick={syncAll} loading={syncing}><Sv d={iRf} s={14}/> Sync All</Btn>
      </div>
    </div>
    {/* Summary stats */}
    {summary&&<div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10,marginBottom:16}}>
      <Card style={{padding:12,display:"flex",justifyContent:"center"}}><Stat l="Total Numbers" v={summary.total} c={C.b}/></Card>
      <Card style={{padding:12,display:"flex",justifyContent:"center"}}><Stat l="Main Numbers" v={summary.main_numbers} c={C.ac}/></Card>
      <Card style={{padding:12,display:"flex",justifyContent:"center"}}><Stat l="Trunks" v={Object.keys(summary.by_trunk||{}).length} c={C.txB}/></Card>
      <Card style={{padding:12,display:"flex",justifyContent:"center"}}><Stat l="PBX Systems" v={Object.keys(summary.by_pbx||{}).length} c={C.g}/></Card>
    </div>}
    {/* Filters */}
    <div style={{display:"flex",gap:10,marginBottom:16}}>
      <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search numbers or names…" style={{flex:1,padding:"8px 12px",fontSize:13,background:C.bg1,border:"1px solid "+C.border,borderRadius:6,color:C.txB,outline:"none",fontFamily:F}}/>
      <select value={typeFilter} onChange={e=>setTypeFilter(e.target.value)} style={{padding:"8px 12px",fontSize:13,background:C.bg1,border:"1px solid "+C.border,borderRadius:6,color:C.txB,outline:"none"}}>
        <option value="">All Types</option><option value="did">DID</option><option value="tollfree">Toll Free</option><option value="international">International</option><option value="internal">Internal</option>
      </select>
    </div>
    {/* Table */}
    <Card><Table cols={[
      {k:"phone_number",l:"Number",r:v=><span style={{fontWeight:600,color:C.txB,fontFamily:M}}>{v}</span>},
      {k:"display_name",l:"Display Name"},
      {k:"pbx_name",l:"System"},
      {k:"trunk_name",l:"Trunk"},
      {k:"number_type",l:"Type",r:v=><Pill status={v==="did"?"info":"skip"} label={v||"did"}/>},
      {k:"inbound_enabled",l:"In",r:v=>v===true?<Sv d={iCk} s={14} c={C.g}/>:v===false?<Sv d={iX} s={14} c={C.r}/>:"—"},
      {k:"outbound_enabled",l:"Out",r:v=>v===true?<Sv d={iCk} s={14} c={C.g}/>:v===false?<Sv d={iX} s={14} c={C.r}/>:"—"},
    ]} data={numbers}/></Card>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   BACKUPS PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function BackupsPage(){
  const[backups,setBackups]=useState([]);
  const[status,setStatus]=useState(null);
  const[loading,setLoading]=useState(true);
  const[pulling,setPulling]=useState({});
  const[toast,setToast]=useState(null);

  const load=()=>{Promise.all([
    api.get("/backups").catch(()=>({backups:[]})),
    api.get("/backups/status").catch(()=>null),
  ]).then(([b,s])=>{setBackups(Array.isArray(b)?b:b.backups||[]);setStatus(s);setLoading(false)})};
  useEffect(()=>{load()},[]);

  const pullLatest=(pbxId)=>{setPulling(p=>({...p,[pbxId]:true}));api.post("/backups/"+pbxId+"/pull").then(()=>{setToast({msg:"Backup pull queued",type:"success"});setTimeout(load,5000)}).catch(()=>setToast({msg:"Pull failed",type:"error"})).finally(()=>setPulling(p=>({...p,[pbxId]:false})))};
  const pullAll=(pbxId)=>{setPulling(p=>({...p,["all_"+pbxId]:true}));api.post("/backups/"+pbxId+"/pull-all").then(r=>{setToast({msg:r.message||"Queued",type:"success"})}).catch(()=>setToast({msg:"Pull failed",type:"error"})).finally(()=>setPulling(p=>({...p,["all_"+pbxId]:false})))};
  const pullAllPbx=()=>{api.post("/backups/pull-all").then(r=>setToast({msg:r.message||"Queued for all systems",type:"success"})).catch(()=>setToast({msg:"Bulk pull failed",type:"error"}))};

  if(loading)return<div style={{textAlign:"center",padding:80}}><Spin/></div>;

  return<div>
    {toast&&<Toast {...toast} onClose={()=>setToast(null)}/>}
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Backups</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{backups.length} downloaded{status?" · "+fBytes(status.total_size_bytes)+" total":""}</p></div>
      <Btn variant="primary" small onClick={pullAllPbx}><Sv d={iDl} s={14}/> Pull All Latest</Btn>
    </div>
    {/* Per-PBX status */}
    {status?.per_pbx?.length>0&&<div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(300px,1fr))",gap:10,marginBottom:22}}>
      {status.per_pbx.map(p=><Card key={p.pbx_id}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:10}}>
          <span style={{fontWeight:600,color:C.txB}}>{p.pbx_name}</span><Pill status={p.health}/>
        </div>
        <div style={{fontSize:12,color:C.txD,marginBottom:8}}>
          {p.latest_backup?<>Last: {fTime(p.latest_backup.downloaded_at)} · {fBytes(p.latest_backup.size_bytes)}</>:"No backups yet"}
          <br/>{p.backup_count} backup{p.backup_count!==1?"s":""} · {fBytes(p.total_size_bytes)}
          {p.schedule&&<><br/>Schedule: {p.schedule.is_enabled?p.schedule.cron_expr:"Disabled"}{p.schedule.next_run_at&&" · Next: "+fTime(p.schedule.next_run_at)}</>}
        </div>
        <div style={{display:"flex",gap:6}}>
          <Btn small onClick={()=>pullLatest(p.pbx_id)} loading={pulling[p.pbx_id]}>Pull Latest</Btn>
          <Btn small variant="ghost" onClick={()=>pullAll(p.pbx_id)} loading={pulling["all_"+p.pbx_id]}>Pull All</Btn>
        </div>
      </Card>)}
    </div>}
    {/* All backups table */}
    <Card><Table cols={[
      {k:"filename",l:"File",r:v=><span style={{fontWeight:500,color:C.txB,fontFamily:M,fontSize:12}}>{v}</span>},
      {k:"backup_type",l:"Type"},
      {k:"created_on_pbx",l:"Created",r:v=>fTime(v)},
      {k:"downloaded_at",l:"Downloaded",r:v=>fTime(v)},
      {k:"size_bytes",l:"Size",r:v=>fBytes(v)},
      {k:"sha256_hash",l:"SHA256",r:v=>v?<span style={{fontFamily:M,fontSize:10,color:C.txM}}>{v.substring(0,16)}…</span>:"—"},
    ]} data={backups}/></Card>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   ALERTS PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function AlertsPage(){
  const[alerts,setAlerts]=useState([]);
  const[filter,setFilter]=useState("firing");
  const[loading,setLoading]=useState(true);

  const load=useCallback(()=>{api.get("/alerts"+(filter?"?state="+filter:"")).then(d=>{setAlerts(Array.isArray(d)?d:d.events||[]);setLoading(false)}).catch(()=>setLoading(false))},[filter]);
  useEffect(()=>{load()},[load]);

  const ack=(id)=>{api.post("/alerts/"+id+"/acknowledge").then(load).catch(()=>{})};

  if(loading)return<div style={{textAlign:"center",padding:80}}><Spin/></div>;

  return<div>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Alerts</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{alerts.length} {filter||"total"}</p></div>
      <div style={{display:"flex",gap:6}}>
        {["firing","acknowledged","resolved",""].map(f=><Btn key={f} small variant={filter===f?"accent":"ghost"} onClick={()=>setFilter(f)}>{f||"All"}</Btn>)}
      </div>
    </div>
    <Card><Table cols={[
      {k:"severity",l:"Severity",r:v=><Pill status={v}/>},
      {k:"title",l:"Alert",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},
      {k:"state",l:"State",r:v=><Pill status={v==="firing"?"error":v==="acknowledged"?"warning":"pass"} label={v}/>},
      {k:"fired_at",l:"Fired",r:v=>fTime(v)},
      {k:"resolved_at",l:"Resolved",r:v=>v?fTime(v):"—"},
      {k:"id",l:"",r:(_,r)=>r.state==="firing"?<Btn small onClick={()=>ack(r.id)}>Acknowledge</Btn>:null},
    ]} data={alerts}/></Card>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   USERS PAGE (admin only)
   ═══════════════════════════════════════════════════════════════════════════ */
function UsersPage(){
  const[users,setUsers]=useState([]);
  const[loading,setLoading]=useState(true);
  const[showAdd,setShowAdd]=useState(false);
  const[form,setForm]=useState({username:"",email:"",password:"",role:"viewer",display_name:""});
  const[saving,setSaving]=useState(false);
  const[toast,setToast]=useState(null);

  const load=()=>{api.get("/users").then(d=>{setUsers(d.users||[]);setLoading(false)}).catch(()=>setLoading(false))};
  useEffect(()=>{load()},[]);

  const addUser=async()=>{
    setSaving(true);
    try{await api.post("/users",form);setShowAdd(false);setForm({username:"",email:"",password:"",role:"viewer",display_name:""});setToast({msg:"User created",type:"success"});load()}
    catch(e){setToast({msg:"Failed to create user",type:"error"})}
    setSaving(false);
  };
  const deactivate=(id)=>{if(confirm("Deactivate this user?"))api.del("/users/"+id).then(()=>{setToast({msg:"User deactivated",type:"success"});load()}).catch(()=>setToast({msg:"Failed",type:"error"}))};
  const resetPw=(id)=>{const pw=prompt("Enter new password (min 8 chars):");if(pw&&pw.length>=8)api.post("/users/"+id+"/reset-password",{new_password:pw}).then(()=>setToast({msg:"Password reset",type:"success"})).catch(()=>setToast({msg:"Failed",type:"error"}))};

  if(loading)return<div style={{textAlign:"center",padding:80}}><Spin/></div>;

  return<div>
    {toast&&<Toast {...toast} onClose={()=>setToast(null)}/>}
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Users</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{users.length} users</p></div>
      <Btn variant="accent" onClick={()=>setShowAdd(true)}><Sv d={iP} s={14}/> Add User</Btn>
    </div>
    <Card><Table cols={[
      {k:"username",l:"Username",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},
      {k:"email",l:"Email"},
      {k:"display_name",l:"Name"},
      {k:"role",l:"Role",r:v=><Pill status={v==="admin"?"error":v==="operator"?"warning":"info"} label={v}/>},
      {k:"auth_method",l:"Auth",r:v=><Pill status={v==="azure_ad"?"info":"skip"} label={v==="azure_ad"?"Azure AD":"Local"}/>},
      {k:"is_active",l:"Active",r:v=>v?<Sv d={iCk} s={14} c={C.g}/>:<Sv d={iX} s={14} c={C.r}/>},
      {k:"last_login",l:"Last Login",r:v=>v?ago(v):"Never"},
      {k:"id",l:"",r:(_,r)=><div style={{display:"flex",gap:4}}>
        {r.auth_method==="local"&&<Btn small variant="ghost" onClick={()=>resetPw(r.id)}>Reset PW</Btn>}
        {r.is_active&&<Btn small variant="danger" onClick={()=>deactivate(r.id)}>Deactivate</Btn>}
      </div>},
    ]} data={users}/></Card>
    {showAdd&&<Modal title="Add User" onClose={()=>setShowAdd(false)}>
      <Input label="Username" value={form.username} onChange={v=>setForm(p=>({...p,username:v}))} required/>
      <Input label="Email" value={form.email} onChange={v=>setForm(p=>({...p,email:v}))} required/>
      <Input label="Display Name" value={form.display_name} onChange={v=>setForm(p=>({...p,display_name:v}))}/>
      <Input label="Password" value={form.password} onChange={v=>setForm(p=>({...p,password:v}))} type="password" required help="Minimum 8 characters"/>
      <Select label="Role" value={form.role} onChange={v=>setForm(p=>({...p,role:v}))} options={[{v:"viewer",l:"Viewer"},{v:"operator",l:"Operator"},{v:"admin",l:"Admin"}]}/>
      <div style={{display:"flex",justifyContent:"flex-end",gap:10,paddingTop:12,borderTop:"1px solid "+C.border}}><Btn variant="ghost" onClick={()=>setShowAdd(false)}>Cancel</Btn><Btn variant="primary" onClick={addUser} loading={saving}>Create User</Btn></div>
    </Modal>}
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   AUDIT LOG PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function AuditPage(){
  const[entries,setEntries]=useState([]);
  const[loading,setLoading]=useState(true);

  useEffect(()=>{api.get("/audit").then(d=>{setEntries(Array.isArray(d)?d:d.entries||[]);setLoading(false)}).catch(()=>setLoading(false))},[]);

  if(loading)return<div style={{textAlign:"center",padding:80}}><Spin/></div>;

  return<div>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Audit Log</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{entries.length} entries</p></div>
      <Btn small onClick={()=>window.open(API+"/audit/export")}>Export CSV</Btn>
    </div>
    <Card><Table cols={[
      {k:"created_at",l:"Time",r:v=><span style={{fontSize:12,fontFamily:M}}>{fTime(v)}</span>},
      {k:"action",l:"Action",r:v=><span style={{fontSize:12,fontFamily:M,color:C.ac}}>{v}</span>},
      {k:"username",l:"User",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},
      {k:"target_type",l:"Target Type"},
      {k:"target_name",l:"Target"},
      {k:"success",l:"Result",r:v=>v?<Pill status="pass" label="OK"/>:<Pill status="fail" label="FAIL"/>},
    ]} data={entries}/></Card>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   SETTINGS PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function SettingsPage(){
  return<div>
    <h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:"0 0 20px"}}>Settings</h1>
    <div style={{display:"grid",gap:12}}>
      <Card><div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:12}}>Security</div><div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,fontSize:13,color:C.txD}}><div><span style={{color:C.txM}}>Encryption:</span> AES-256-GCM</div><div><span style={{color:C.txM}}>Key source:</span> MASTER_KEY env var</div><div><span style={{color:C.txM}}>JWT expiry:</span> 60 min</div><div><span style={{color:C.txM}}>Login lockout:</span> 5 attempts / 15 min</div></div></Card>
      <Card><div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:12}}>Polling</div><div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,fontSize:13,color:C.txD}}><div><span style={{color:C.txM}}>Default interval:</span> 60s</div><div><span style={{color:C.txM}}>Max backoff:</span> 600s</div><div><span style={{color:C.txM}}>Alert check:</span> 30s</div><div><span style={{color:C.txM}}>Capability reprobe:</span> Weekly</div></div></Card>
      <Card><div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:12}}>Azure AD SSO</div><div style={{fontSize:13,color:C.txD}}>Configure via environment variables: AZURE_AD_ENABLED, AZURE_AD_TENANT_ID, AZURE_AD_CLIENT_ID, AZURE_AD_CLIENT_SECRET</div></Card>
      <Card><div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:12}}>Database</div><div style={{fontSize:13,color:C.txD,fontFamily:M,fontSize:12}}>PostgreSQL 16 · Audit log: immutable (trigger-protected) · Poll history: 90-day retention</div></Card>
    </div>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   APP SHELL
   ═══════════════════════════════════════════════════════════════════════════ */
export default function App(){
  const[authed,setAuthed]=useState(!!localStorage.getItem("token"));
  const[page,setPage]=useState("dashboard");
  const[showAdd,setShowAdd]=useState(false);

  const user=JSON.parse(localStorage.getItem("user")||'{"role":"viewer"}');
  const isAdmin=user.role==="admin";

  useEffect(()=>{const h=()=>setAuthed(!!localStorage.getItem("token"));window.addEventListener("auth-change",h);return()=>window.removeEventListener("auth-change",h)},[]);

  // Handle SSO callback — extract token from URL query params
  useEffect(()=>{
    const params=new URLSearchParams(window.location.search);
    const token=params.get("access_token");
    if(token){localStorage.setItem("token",token);const u=params.get("user");if(u)try{localStorage.setItem("user",u)}catch(e){}window.history.replaceState({},"","/");setAuthed(true)}
  },[]);

  const logout=()=>{localStorage.removeItem("token");localStorage.removeItem("user");setAuthed(false)};

  if(!authed)return<LoginPage onLogin={()=>setAuthed(true)}/>;

  const nav=[
    {id:"dashboard",l:"Dashboard",d:"M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0v-4a1 1 0 011-1h2a1 1 0 011 1v4"},
    {id:"systems",l:"Systems",d:"M4 6h16M4 6a2 2 0 012-2h12a2 2 0 012 2M4 6v4a2 2 0 002 2h12a2 2 0 002-2V6M6 8h.01M6 16h.01M4 14h16v4a2 2 0 01-2 2H6a2 2 0 01-2-2v-4"},
    {id:"phone-numbers",l:"Phone Numbers",d:iPhone},
    {id:"backups",l:"Backups",d:iDl},
    {id:"alerts",l:"Alerts",d:"M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6 6 0 00-5-5.917V4a1 1 0 10-2 0v1.083A6 6 0 006 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0a3 3 0 11-6 0"},
    {id:"audit",l:"Audit Log",d:"M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"},
    ...(isAdmin?[{id:"users",l:"Users",d:iUser}]:[]),
    {id:"settings",l:"Settings",d:"M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z"},
  ];

  const renderPage=()=>{
    switch(page){
      case"dashboard":return<DashboardPage onSelectSystem={()=>setPage("systems")} onAdd={()=>setShowAdd(true)}/>;
      case"systems":return<SystemsPage onAdd={()=>setShowAdd(true)}/>;
      case"phone-numbers":return<PhoneNumbersPage/>;
      case"backups":return<BackupsPage/>;
      case"alerts":return<AlertsPage/>;
      case"audit":return<AuditPage/>;
      case"users":return isAdmin?<UsersPage/>:null;
      case"settings":return<SettingsPage/>;
      default:return<DashboardPage onSelectSystem={()=>setPage("systems")} onAdd={()=>setShowAdd(true)}/>;
    }
  };

  return<div style={{display:"flex",height:"100vh",background:C.bg0,color:C.tx,fontFamily:F,fontSize:14}}>
    <nav style={{width:210,background:C.bg1,borderRight:"1px solid "+C.border,display:"flex",flexDirection:"column",padding:"14px 0",flexShrink:0}}>
      <div style={{padding:"2px 18px 18px",borderBottom:"1px solid "+C.border,marginBottom:6}}>
        <div style={{fontSize:16,fontWeight:800,color:C.txB,letterSpacing:"-.02em"}}>PBXMonitor<span style={{color:C.ac}}>X</span></div>
        <div style={{fontSize:10,color:C.txM,marginTop:2,fontFamily:M}}>3CX v20 · {user.username}</div>
      </div>
      {nav.map(n=>{const active=page===n.id;return<button key={n.id} onClick={()=>setPage(n.id)} style={{display:"flex",alignItems:"center",gap:10,padding:"9px 18px",margin:"1px 8px",borderRadius:6,border:"none",cursor:"pointer",fontFamily:F,fontSize:13,fontWeight:active?600:400,color:active?C.txB:C.txD,background:active?C.acBg:"transparent",transition:"all .12s",textAlign:"left"}}><Sv d={n.d} s={16} c={active?C.ac:C.txD}/>{n.l}</button>})}
      <div style={{flex:1}}/>
      <button onClick={logout} style={{display:"flex",alignItems:"center",gap:10,padding:"9px 18px",margin:"1px 8px",borderRadius:6,border:"none",cursor:"pointer",fontFamily:F,fontSize:13,color:C.txD,background:"transparent"}}><Sv d={iLogout} s={16} c={C.txD}/> Logout</button>
      <div style={{padding:"10px 18px",borderTop:"1px solid "+C.border,fontSize:10,color:C.txM,fontFamily:M}}>v0.2.0 · <span style={{color:C.g}}>●</span> {user.role}</div>
    </nav>
    <main style={{flex:1,overflow:"auto",padding:"24px 32px"}}>{renderPage()}</main>
    {showAdd&&<AddInstanceModal onClose={()=>setShowAdd(false)} onSave={()=>{setShowAdd(false);setPage("systems")}}/>}
    <style>{`
      @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700;800&display=swap');
      @keyframes spin{to{transform:rotate(360deg)}}
      @keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
      *{box-sizing:border-box;margin:0;padding:0}
      ::-webkit-scrollbar{width:6px;height:6px}
      ::-webkit-scrollbar-track{background:${C.bg0}}
      ::-webkit-scrollbar-thumb{background:${C.border};border-radius:3px}
      ::-webkit-scrollbar-thumb:hover{background:${C.borderL}}
      input::placeholder,select{color:${C.txM}}
    `}</style>
  </div>;
}
