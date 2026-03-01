import { useState, useEffect, useRef, useCallback } from "react";

/* ═══════════════════════════════════════════════════════════════════════════
   THEME & UTILITIES
   ═══════════════════════════════════════════════════════════════════════════ */
const C = { bg0:"#0A0A08",bg1:"#111110",bg2:"#1A1918",bg3:"#222120",border:"#2C2A28",borderL:"#3A3836",tx:"#D4D0CB",txD:"#8A8580",txM:"#5E5A55",txB:"#EDE9E4",ac:"#C8965A",acD:"#A0784A",acBg:"rgba(200,150,90,.08)",g:"#2ECC71",gB:"rgba(46,204,113,.1)",y:"#F1C40F",yB:"rgba(241,196,15,.1)",r:"#E74C3C",rB:"rgba(231,76,60,.1)",b:"#3498DB",bB:"rgba(52,152,219,.1)" };
const F = `"IBM Plex Sans",system-ui,sans-serif`, M = `"IBM Plex Mono","Consolas",monospace`;

const ago=(iso)=>{if(!iso)return"\u2014";const m=Math.floor((Date.now()-new Date(iso))/60000);if(m<1)return"now";if(m<60)return m+"m";const h=Math.floor(m/60);return h<24?h+"h":Math.floor(h/24)+"d"};
const fDate=(iso)=>iso?new Date(iso).toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"}):"\u2014";
const fTime=(iso)=>iso?new Date(iso).toLocaleString("en-US",{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"}):"\u2014";
const fBytes=(b)=>{if(!b)return"\u2014";if(b>1e9)return(b/1e9).toFixed(1)+" GB";if(b>1e6)return(b/1e6).toFixed(0)+" MB";return(b/1024).toFixed(0)+" KB"};
const sc=(s)=>({healthy:C.g,registered:C.g,online:C.g,available:C.g,pass:C.g,warning:C.y,degraded:C.y,warn:C.y,error:C.r,unregistered:C.r,offline:C.r,unavailable:C.r,critical:C.r,fail:C.r,firing:C.r,acknowledged:C.y,resolved:C.g,info:C.b,skip:C.txM,untested:C.txM,active:C.g,inactive:C.r,local:C.b,azure_ad:C.ac,admin:C.ac,operator:C.b,viewer:C.txD}[s]||C.txM);
const sbg=(s)=>({healthy:C.gB,registered:C.gB,online:C.gB,available:C.gB,pass:C.gB,warning:C.yB,degraded:C.yB,warn:C.yB,error:C.rB,unregistered:C.rB,offline:C.rB,unavailable:C.rB,critical:C.rB,fail:C.rB,firing:C.rB,acknowledged:C.yB,resolved:C.gB,info:C.bB,active:C.gB,inactive:C.rB,local:C.bB,azure_ad:C.acBg,admin:C.acBg,operator:C.bB,viewer:"rgba(94,90,85,.06)"}[s]||"rgba(94,90,85,.06)");

/* ═══════════════════════════════════════════════════════════════════════════
   API CLIENT
   ═══════════════════════════════════════════════════════════════════════════ */
const API = "/api";
const headers = () => ({
  "Content-Type": "application/json",
  ...(localStorage.getItem("token") ? { Authorization: `Bearer ${localStorage.getItem("token")}` } : {})
});
const handleRes = async (r) => {
  if (r.status === 401) {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    window.dispatchEvent(new Event("auth-logout"));
    return Promise.reject(r);
  }
  if (!r.ok) return Promise.reject(r);
  const text = await r.text();
  return text ? JSON.parse(text) : {};
};
const api = {
  get: (path) => fetch(API + path, { headers: headers() }).then(handleRes),
  post: (path, body) => fetch(API + path, { method: "POST", headers: headers(), body: JSON.stringify(body) }).then(handleRes),
  patch: (path, body) => fetch(API + path, { method: "PATCH", headers: headers(), body: JSON.stringify(body) }).then(handleRes),
  put: (path, body) => fetch(API + path, { method: "PUT", headers: headers(), body: JSON.stringify(body) }).then(handleRes),
  del: (path) => fetch(API + path, { method: "DELETE", headers: headers() }).then(r => { if(r.status===401){localStorage.removeItem("token");localStorage.removeItem("user");window.dispatchEvent(new Event("auth-logout"));return Promise.reject(r);} if(!r.ok)return Promise.reject(r); return r; }),
};

/* ═══════════════════════════════════════════════════════════════════════════
   ICONS
   ═══════════════════════════════════════════════════════════════════════════ */
const iCk="M5 13l4 4L19 7",iX="M6 18L18 6M6 6l12 12",iDl="M12 4v12m0 0l-4-4m4 4l4-4M4 18h16",iRf="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15",iP="M12 4v16m8-8H4",iLk="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z",iSh="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",iW="M12 9v2m0 4h.01M5.07 19h13.86c1.54 0 2.5-1.67 1.73-3L13.73 4c-.77-1.33-2.69-1.33-3.46 0L3.34 16c-.77 1.33.19 3 1.73 3z",iEye="M15 12a3 3 0 11-6 0 3 3 0 016 0zM2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z",iEyeX="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M3 3l18 18";
const iUser="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z";
const iPhone="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z";
const iLogout="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1";
const iEdit="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z";
const iTrash="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16";

/* ═══════════════════════════════════════════════════════════════════════════
   SHARED COMPONENTS
   ═══════════════════════════════════════════════════════════════════════════ */
const Pill=({status,label})=><span style={{display:"inline-flex",alignItems:"center",gap:5,padding:"2px 10px",borderRadius:99,fontSize:11,fontWeight:600,letterSpacing:".04em",textTransform:"uppercase",color:sc(status),background:sbg(status),whiteSpace:"nowrap"}}><span style={{width:6,height:6,borderRadius:"50%",background:sc(status)}}/>{label||status}</span>;
const Stat=({l,v,c})=><div style={{textAlign:"center"}}><div style={{fontSize:20,fontWeight:700,color:c||C.txB,fontFamily:M}}>{v}</div><div style={{fontSize:9,color:C.txM,textTransform:"uppercase",letterSpacing:".06em",marginTop:3,fontWeight:600}}>{l}</div></div>;
const Sv=({d,s=18,c="currentColor"})=><svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={d}/></svg>;
const Spinner=({size=20})=><span style={{display:"inline-block",width:size,height:size,border:"2px solid "+C.border,borderTopColor:C.ac,borderRadius:"50%",animation:"spin .6s linear infinite"}}/>;
const PageLoader=()=><div style={{display:"flex",justifyContent:"center",alignItems:"center",padding:60}}><Spinner size={28}/></div>;
const ErrorMsg=({msg,onRetry})=><div style={{padding:20,background:C.rB,border:"1px solid rgba(231,76,60,.2)",borderRadius:8,margin:"12px 0"}}><div style={{display:"flex",gap:10,alignItems:"center"}}><Sv d={iW} s={18} c={C.r}/><span style={{color:C.r,fontWeight:600,fontSize:14}}>{msg}</span>{onRetry&&<Btn small variant="ghost" onClick={onRetry}>Retry</Btn>}</div></div>;

function Btn({children,variant="default",onClick,small,disabled,loading,style:sx,type}){const[h,setH]=useState(false);const v={default:{bg:C.bg3,bh:"#2E2C2A",bc:C.borderL,c:C.tx},primary:{bg:"#1B6B3A",bh:"#1E8045",bc:"#1B6B3A",c:"#fff"},danger:{bg:"#6B1A1A",bh:"#801F1F",bc:"#6B1A1A",c:"#FCA5A5"},ghost:{bg:"transparent",bh:"rgba(255,255,255,.04)",bc:"transparent",c:C.txD},accent:{bg:C.acD,bh:C.ac,bc:C.acD,c:"#fff"}}[variant];return<button type={type||"button"} onClick={onClick} disabled={disabled||loading} onMouseEnter={()=>setH(true)} onMouseLeave={()=>setH(false)} style={{display:"inline-flex",alignItems:"center",justifyContent:"center",gap:6,padding:small?"5px 12px":"9px 18px",fontSize:small?12:13,fontWeight:600,background:disabled?C.bg2:h?v.bh:v.bg,border:"1px solid "+(disabled?C.border:v.bc),borderRadius:6,color:disabled?C.txM:v.c,cursor:disabled?"not-allowed":"pointer",transition:"all .12s",fontFamily:F,opacity:disabled?.5:1,...sx}}>{loading&&<Spinner size={14}/>}{children}</button>}

function Card({children,style,onClick,hv}){const[h,setH]=useState(false);return<div onClick={onClick} onMouseEnter={()=>setH(true)} onMouseLeave={()=>setH(false)} style={{background:h&&hv?C.bg3:C.bg2,border:"1px solid "+C.border,borderRadius:8,padding:20,cursor:onClick?"pointer":"default",transition:"all .15s",transform:h&&hv?"translateY(-1px)":"none",boxShadow:h&&hv?"0 6px 24px rgba(0,0,0,.4)":"none",...style}}>{children}</div>}

function Table({cols,data}){return<div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}><thead><tr>{cols.map(c=><th key={c.k} style={{textAlign:"left",padding:"10px 14px",borderBottom:"1px solid "+C.border,fontSize:10,textTransform:"uppercase",letterSpacing:".06em",color:C.txM,fontWeight:700}}>{c.l}</th>)}</tr></thead><tbody>{data.map((r,i)=><tr key={r.id||i} style={{borderBottom:"1px solid rgba(44,42,40,.4)"}}>{cols.map(c=><td key={c.k} style={{padding:"10px 14px",color:C.tx}}>{c.r?c.r(r[c.k],r):(r[c.k]||"\u2014")}</td>)}</tr>)}{data.length===0&&<tr><td colSpan={cols.length} style={{padding:40,textAlign:"center",color:C.txM}}>No data</td></tr>}</tbody></table></div>}

function Input({label,value,onChange,type="text",placeholder,help,error,mono,required,icon,disabled}){const[show,setShow]=useState(false);const isPass=type==="password";return<div style={{marginBottom:16}}>{label&&<label style={{display:"block",fontSize:11,fontWeight:600,color:C.txD,textTransform:"uppercase",letterSpacing:".05em",marginBottom:5}}>{label}{required&&<span style={{color:C.r}}>*</span>}</label>}<div style={{position:"relative"}}><input type={isPass&&show?"text":type} value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder} disabled={disabled} style={{width:"100%",padding:"9px 12px",paddingRight:isPass?36:12,fontSize:13,fontFamily:mono?M:F,background:C.bg1,border:"1px solid "+(error?C.r:C.border),borderRadius:6,color:C.txB,outline:"none",boxSizing:"border-box",transition:"border-color .15s",opacity:disabled?.5:1}} onFocus={e=>e.target.style.borderColor=C.ac} onBlur={e=>e.target.style.borderColor=error?C.r:C.border}/>{isPass&&<button type="button" onClick={()=>setShow(!show)} style={{position:"absolute",right:8,top:"50%",transform:"translateY(-50%)",background:"none",border:"none",cursor:"pointer",padding:2}}><Sv d={show?iEyeX:iEye} s={16} c={C.txM}/></button>}</div>{help&&!error&&<div style={{fontSize:11,color:C.txM,marginTop:3}}>{help}</div>}{error&&<div style={{fontSize:11,color:C.r,marginTop:3}}>{error}</div>}</div>}

function Select({label,value,onChange,options,help}){return<div style={{marginBottom:16}}>{label&&<label style={{display:"block",fontSize:11,fontWeight:600,color:C.txD,textTransform:"uppercase",letterSpacing:".05em",marginBottom:5}}>{label}</label>}<select value={value} onChange={e=>onChange(e.target.value)} style={{width:"100%",padding:"9px 12px",fontSize:13,fontFamily:F,background:C.bg1,border:"1px solid "+C.border,borderRadius:6,color:C.txB,outline:"none",cursor:"pointer"}}>{options.map(o=><option key={o.v} value={o.v}>{o.l}</option>)}</select>{help&&<div style={{fontSize:11,color:C.txM,marginTop:3}}>{help}</div>}</div>}

/* ═══════════════════════════════════════════════════════════════════════════
   MODAL WRAPPER
   ═══════════════════════════════════════════════════════════════════════════ */
function Modal({onClose,title,subtitle,width=560,children}){
  return<div style={{position:"fixed",inset:0,zIndex:1000,display:"flex",alignItems:"center",justifyContent:"center"}}>
    <div style={{position:"absolute",inset:0,background:"rgba(0,0,0,.7)",backdropFilter:"blur(4px)"}} onClick={onClose}/>
    <div style={{position:"relative",background:C.bg1,border:"1px solid "+C.border,borderRadius:12,width,maxHeight:"90vh",overflow:"auto",boxShadow:"0 20px 60px rgba(0,0,0,.6)"}}>
      <div style={{padding:"20px 24px",borderBottom:"1px solid "+C.border,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
        <div><div style={{fontSize:17,fontWeight:700,color:C.txB}}>{title}</div>{subtitle&&<div style={{fontSize:12,color:C.txM,marginTop:2}}>{subtitle}</div>}</div>
        <button onClick={onClose} style={{background:"none",border:"none",cursor:"pointer",padding:4}}><Sv d={iX} s={20} c={C.txM}/></button>
      </div>
      <div style={{padding:"20px 24px"}}>{children}</div>
    </div>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   LOGIN PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function LoginPage({onLogin}){
  const[username,setUsername]=useState("");
  const[password,setPassword]=useState("");
  const[loading,setLoading]=useState(false);
  const[error,setError]=useState("");
  const[ssoEnabled,setSsoEnabled]=useState(false);

  useEffect(()=>{
    api.get("/auth/sso/config").then(d=>{if(d&&d.enabled)setSsoEnabled(true)}).catch(()=>{});
  },[]);

  const doLogin=async(e)=>{
    e.preventDefault();
    if(!username||!password){setError("Username and password required");return;}
    setLoading(true);setError("");
    try{
      const res=await api.post("/auth/login",{username,password});
      localStorage.setItem("token",res.access_token);
      localStorage.setItem("user",JSON.stringify(res.user));
      onLogin(res.user);
    }catch(err){
      let msg="Login failed";
      try{const b=await err.json();msg=b.detail||msg;}catch{}
      setError(msg);
    }finally{setLoading(false);}
  };

  return<div style={{display:"flex",alignItems:"center",justifyContent:"center",height:"100vh",background:C.bg0,fontFamily:F}}>
    <div style={{width:380,background:C.bg1,border:"1px solid "+C.border,borderRadius:12,padding:32,boxShadow:"0 20px 60px rgba(0,0,0,.5)"}}>
      <div style={{textAlign:"center",marginBottom:28}}>
        <div style={{fontSize:24,fontWeight:800,color:C.txB,letterSpacing:"-.02em"}}>PBXMonitor<span style={{color:C.ac}}>X</span></div>
        <div style={{fontSize:12,color:C.txM,marginTop:4}}>3CX Monitor & Backup Management</div>
      </div>
      <form onSubmit={doLogin}>
        <Input label="Username" value={username} onChange={setUsername} placeholder="admin" required/>
        <Input label="Password" value={password} onChange={setPassword} type="password" placeholder="Enter password" required/>
        {error&&<div style={{fontSize:12,color:C.r,marginBottom:12,padding:"8px 12px",background:C.rB,borderRadius:6}}>{error}</div>}
        <Btn variant="accent" type="submit" loading={loading} style={{width:"100%",marginTop:4}}>Sign In</Btn>
      </form>
      {ssoEnabled&&<>
        <div style={{display:"flex",alignItems:"center",gap:12,margin:"20px 0"}}><div style={{flex:1,height:1,background:C.border}}/><span style={{fontSize:11,color:C.txM}}>OR</span><div style={{flex:1,height:1,background:C.border}}/></div>
        <Btn variant="default" onClick={()=>{window.location.href="/api/auth/sso/login"}} style={{width:"100%"}}>
          <Sv d="M5.5 3.5h5v5h-5zM13.5 3.5h5v5h-5zM5.5 11.5h5v5h-5zM13.5 11.5h5v5h-5z" s={16} c={C.b}/>
          Sign in with Microsoft
        </Btn>
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
    try{
      const res=await api.post("/pbx/test-connection",{
        base_url:form.base_url.trim().replace(/\/$/,""),
        username:form.username,
        password:form.password,
        tls_policy:form.tls_policy,
      });
      setTestSteps(res.steps||[]);
      setTestResult({
        success:res.success,
        version:res.version,
        message:res.message,
        capabilities:res.capabilities||[],
      });
      setStep("results");
    }catch(err){
      let msg="Connection test failed";
      try{const b=await err.json();msg=b.detail||msg;}catch{}
      setTestResult({success:false,message:msg});
      setStep("results");
    }
  };

  const saveInstance=async()=>{
    setSaving(true);
    try{
      await api.post("/pbx/instances",{
        name:form.name.trim(),
        base_url:form.base_url.trim().replace(/\/$/,""),
        username:form.username,
        password:form.password,
        tls_policy:form.tls_policy,
        poll_interval_s:form.poll_interval_s,
        notes:form.notes,
        detected_version:testResult?.version||null,
        capabilities:testResult?.capabilities?.map(c=>({feature:c.feature,status:c.status,method:c.method}))||[],
      });
      onSave();
      onClose();
    }catch(err){
      let msg="Failed to save";
      try{const b=await err.json();msg=b.detail||msg;}catch{}
      alert(msg);
    }finally{setSaving(false);}
  };

  return<div style={{position:"fixed",inset:0,zIndex:1000,display:"flex",alignItems:"center",justifyContent:"center"}}>
    <div style={{position:"absolute",inset:0,background:"rgba(0,0,0,.7)",backdropFilter:"blur(4px)"}} onClick={onClose}/>
    <div style={{position:"relative",background:C.bg1,border:"1px solid "+C.border,borderRadius:12,width:560,maxHeight:"90vh",overflow:"auto",boxShadow:"0 20px 60px rgba(0,0,0,.6)"}}>
      <div style={{padding:"20px 24px",borderBottom:"1px solid "+C.border,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
        <div>
          <div style={{fontSize:17,fontWeight:700,color:C.txB}}>Add PBX System</div>
          <div style={{fontSize:12,color:C.txM,marginTop:2}}>
            {step==="form"?"Enter connection details":step==="testing"?"Testing connectivity...":step==="results"?(testResult?.success?"Connection verified":"Connection failed"):""}
          </div>
        </div>
        <button onClick={onClose} style={{background:"none",border:"none",cursor:"pointer",padding:4}}><Sv d={iX} s={20} c={C.txM}/></button>
      </div>
      <div style={{padding:"20px 24px"}}>
        {step==="form"&&<>
          <div style={{display:"flex",gap:10,padding:12,background:C.acBg,border:"1px solid rgba(200,150,90,.15)",borderRadius:6,marginBottom:20,fontSize:12,color:C.ac}}>
            <Sv d={iSh} s={18} c={C.ac}/>
            <div><strong>Credentials encrypted at rest</strong> with AES-256-GCM. Passwords never stored in plaintext.</div>
          </div>
          <Input label="System Name" value={form.name} onChange={v=>upd("name",v)} placeholder="e.g. HQ Production PBX" error={errors.name} required/>
          <Input label="PBX URL" value={form.base_url} onChange={v=>upd("base_url",v)} placeholder="https://pbx.example.com:5001" help="Full HTTPS URL to the 3CX management console" error={errors.base_url} mono required/>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
            <Input label="Admin Username" value={form.username} onChange={v=>upd("username",v)} placeholder="admin" error={errors.username} required/>
            <Input label="Password" value={form.password} onChange={v=>upd("password",v)} type="password" placeholder="Password" error={errors.password} required/>
          </div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
            <Select label="TLS Verification" value={form.tls_policy} onChange={v=>upd("tls_policy",v)} options={[{v:"verify",l:"Verify Certificate (Recommended)"},{v:"trust_self_signed",l:"Trust Self-Signed"}]} help={form.tls_policy==="trust_self_signed"?"Warning: Less secure":"Strict TLS certificate verification"}/>
            <Select label="Poll Interval" value={form.poll_interval_s} onChange={v=>upd("poll_interval_s",+v)} options={[{v:60,l:"60 seconds (Recommended)"},{v:300,l:"5 minutes"},{v:600,l:"10 minutes"},{v:3600,l:"60 minutes"}]}/>
          </div>
          <Input label="Notes" value={form.notes} onChange={v=>upd("notes",v)} placeholder="Optional description or location..."/>
          {form.tls_policy==="trust_self_signed"&&<div style={{display:"flex",gap:10,padding:12,background:C.rB,border:"1px solid rgba(231,76,60,.2)",borderRadius:6,marginBottom:16,fontSize:12,color:C.r}}>
            <Sv d={iW} s={18} c={C.r}/>
            <div><strong>Self-signed certificate trust enabled.</strong> Only use for development or isolated lab environments.</div>
          </div>}
          <div style={{display:"flex",justifyContent:"flex-end",gap:10,paddingTop:8,borderTop:"1px solid "+C.border}}>
            <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
            <Btn variant="accent" onClick={runTest}><Sv d={iSh} s={14}/> Test Connection</Btn>
          </div>
        </>}

        {step==="testing"&&<div>
          <div style={{marginBottom:16,fontSize:13,color:C.txD}}>Validating connectivity and discovering capabilities...</div>
          {testSteps.map((s,i)=><div key={i} style={{display:"flex",alignItems:"flex-start",gap:10,padding:"8px 0",borderBottom:"1px solid rgba(44,42,40,.3)",animation:"fadeIn .3s ease"}}>
            <div style={{marginTop:2,flexShrink:0}}>
              {s.status==="pass"?<Sv d={iCk} s={16} c={C.g}/>:s.status==="fail"?<Sv d={iX} s={16} c={C.r}/>:<Spinner size={16}/>}
            </div>
            <div style={{flex:1}}>
              <div style={{fontSize:12,fontWeight:600,color:s.status==="fail"?C.r:C.txB}}>{s.step.replace(/_/g," ")}</div>
              <div style={{fontSize:11,color:C.txD,marginTop:1,fontFamily:M}}>{s.message}</div>
            </div>
            {s.duration_ms>0&&<div style={{fontSize:10,color:C.txM,fontFamily:M,flexShrink:0}}>{s.duration_ms}ms</div>}
          </div>)}
          <div style={{textAlign:"center",padding:16}}><Spinner/></div>
        </div>}

        {step==="results"&&<div>
          <div style={{display:"flex",gap:12,padding:14,background:testResult.success?C.gB:C.rB,border:"1px solid "+(testResult.success?"rgba(46,204,113,.2)":"rgba(231,76,60,.2)"),borderRadius:8,marginBottom:18}}>
            <div style={{marginTop:1}}>{testResult.success?<Sv d={iCk} s={22} c={C.g}/>:<Sv d={iX} s={22} c={C.r}/>}</div>
            <div>
              <div style={{fontSize:15,fontWeight:700,color:testResult.success?C.g:C.r}}>{testResult.success?"Connection Successful":"Connection Failed"}</div>
              <div style={{fontSize:12,color:C.txD,marginTop:2}}>{testResult.message}</div>
              {testResult.version&&<div style={{fontSize:11,color:C.txM,marginTop:2,fontFamily:M}}>3CX Version: {testResult.version}</div>}
            </div>
          </div>
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
          {testSteps.length>0&&<details style={{marginBottom:18}}>
            <summary style={{fontSize:11,fontWeight:600,color:C.txM,cursor:"pointer",textTransform:"uppercase",letterSpacing:".05em"}}>Connection Steps ({testSteps.length})</summary>
            <div style={{marginTop:8}}>
              {testSteps.map((s,i)=><div key={i} style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0",fontSize:12}}>
                <span style={{width:6,height:6,borderRadius:"50%",background:sc(s.status)}}/>
                <span style={{color:C.txD,fontFamily:M}}>{s.message}</span>
              </div>)}
            </div>
          </details>}
          <div style={{display:"flex",justifyContent:"flex-end",gap:10,paddingTop:12,borderTop:"1px solid "+C.border}}>
            <Btn variant="ghost" onClick={()=>{setStep("form");setTestResult(null);setTestSteps([])}}>Edit Details</Btn>
            {!testResult.success&&<Btn variant="accent" onClick={runTest}><Sv d={iRf} s={14}/> Retry</Btn>}
            {testResult.success&&<Btn variant="primary" onClick={saveInstance} loading={saving}><Sv d={iCk} s={14}/> Save System</Btn>}
          </div>
        </div>}
      </div>
    </div>
    <style>{`@keyframes spin{to{transform:rotate(360deg)}} @keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}`}</style>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   EDIT INSTANCE MODAL
   ═══════════════════════════════════════════════════════════════════════════ */
function EditInstanceModal({inst,onClose,onSave}){
  const[form,setForm]=useState({name:inst.name||"",tls_policy:inst.tls_policy||"verify",poll_interval_s:inst.poll_interval_s||60,notes:inst.notes||"",is_enabled:inst.is_enabled!==false,password:""});
  const[saving,setSaving]=useState(false);
  const upd=(k,v)=>setForm(p=>({...p,[k]:v}));

  const save=async()=>{
    setSaving(true);
    try{
      const body={name:form.name,tls_policy:form.tls_policy,poll_interval_s:form.poll_interval_s,notes:form.notes,is_enabled:form.is_enabled};
      if(form.password)body.password=form.password;
      await api.patch("/pbx/instances/"+inst.id,body);
      onSave();onClose();
    }catch(err){
      let msg="Save failed";try{const b=await err.json();msg=b.detail||msg;}catch{}
      alert(msg);
    }finally{setSaving(false);}
  };

  return<Modal onClose={onClose} title="Edit System" subtitle={inst.name}>
    <Input label="Name" value={form.name} onChange={v=>upd("name",v)} required/>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Select label="TLS Policy" value={form.tls_policy} onChange={v=>upd("tls_policy",v)} options={[{v:"verify",l:"Verify Certificate"},{v:"trust_self_signed",l:"Trust Self-Signed"}]}/>
      <Select label="Poll Interval" value={form.poll_interval_s} onChange={v=>upd("poll_interval_s",+v)} options={[{v:60,l:"60 seconds"},{v:300,l:"5 minutes"},{v:600,l:"10 minutes"},{v:3600,l:"60 minutes"}]}/>
    </div>
    <Input label="New Password" value={form.password} onChange={v=>upd("password",v)} type="password" placeholder="Leave blank to keep current" help="Only set if you need to change the PBX password"/>
    <Input label="Notes" value={form.notes} onChange={v=>upd("notes",v)} placeholder="Optional"/>
    <div style={{marginBottom:16}}><label style={{display:"flex",alignItems:"center",gap:8,cursor:"pointer"}}>
      <input type="checkbox" checked={form.is_enabled} onChange={e=>upd("is_enabled",e.target.checked)} style={{accentColor:C.ac}}/>
      <span style={{fontSize:13,color:C.txB}}>Polling Enabled</span>
    </label></div>
    <div style={{display:"flex",justifyContent:"flex-end",gap:10,paddingTop:12,borderTop:"1px solid "+C.border}}>
      <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
      <Btn variant="primary" onClick={save} loading={saving}>Save Changes</Btn>
    </div>
  </Modal>;
}


/* ═══════════════════════════════════════════════════════════════════════════
   DASHBOARD PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function DashboardPage({onNavigate}){
  const[instances,setInstances]=useState([]);
  const[statuses,setStatuses]=useState({});
  const[alerts,setAlerts]=useState([]);
  const[backups,setBackups]=useState([]);
  const[phoneCount,setPhoneCount]=useState(0);
  const[loading,setLoading]=useState(true);
  const[error,setError]=useState("");

  const load=useCallback(async()=>{
    try{
      const[inst,al,bk]=await Promise.all([
        api.get("/pbx/instances"),
        api.get("/alerts?state=firing&limit=5"),
        api.get("/backups?limit=50"),
      ]);
      setInstances(inst||[]);
      setAlerts(al||[]);
      setBackups(bk||[]);
      // Load status for each instance
      const sMap={};
      await Promise.all((inst||[]).map(async(i)=>{
        try{const s=await api.get("/pbx/instances/"+i.id+"/status");sMap[i.id]=s;}catch{}
      }));
      setStatuses(sMap);
      // Phone number count
      try{const pn=await api.get("/phone-numbers/summary");setPhoneCount(pn.total||0);}catch{setPhoneCount(0);}
      setError("");
    }catch(e){setError("Failed to load dashboard data");}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{load();const iv=setInterval(load,30000);return()=>clearInterval(iv);},[load]);

  if(loading)return<PageLoader/>;
  if(error)return<ErrorMsg msg={error} onRetry={load}/>;

  const firingAlerts=(alerts||[]).filter(a=>a.state==="firing");
  const totalTrunks=Object.values(statuses).reduce((a,s)=>a+(s.trunks?.length||0),0);
  const healthySystems=instances.filter(i=>{const s=statuses[i.id];return s&&s.overall_health==="healthy"}).length;
  const backedUpSystems=new Set((backups||[]).filter(b=>{
    if(!b.downloaded_at)return false;
    const age=(Date.now()-new Date(b.downloaded_at).getTime())/3600000;
    return age<24;
  }).map(b=>b.pbx_id)).size;

  return<div>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Dashboard</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{instances.length} system{instances.length!==1?"s":""} monitored</p></div>
      <Btn variant="ghost" small onClick={load}><Sv d={iRf} s={14}/> Refresh</Btn>
    </div>

    {/* Top Stats */}
    <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10,marginBottom:22}}>
      <Card style={{padding:14,display:"flex",justifyContent:"center"}}><Stat l="PBX Systems" v={instances.length} c={healthySystems===instances.length?C.g:C.y}/></Card>
      <Card style={{padding:14,display:"flex",justifyContent:"center"}}><Stat l="Active Alerts" v={firingAlerts.length} c={firingAlerts.length>0?C.r:C.g}/></Card>
      <Card style={{padding:14,display:"flex",justifyContent:"center"}}><Stat l="Backup Health" v={`${backedUpSystems}/${instances.length}`} c={backedUpSystems>=instances.length?C.g:C.y}/></Card>
      <Card style={{padding:14,display:"flex",justifyContent:"center"}}><Stat l="Phone Numbers" v={phoneCount} c={C.b}/></Card>
    </div>

    {/* System Status Cards */}
    {instances.length>0&&<>
      <div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:10}}>System Status</div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(360px,1fr))",gap:12,marginBottom:22}}>
        {instances.map(inst=>{
          const s=statuses[inst.id]||{};
          const health=s.overall_health||"unknown";
          const trunks=s.trunks||[];
          const sbcs=s.sbcs||[];
          const lic=s.license||{};
          const trunkUp=trunks.filter(t=>t.status==="registered").length;
          const sbcUp=sbcs.filter(sb=>sb.status==="online").length;
          return<Card key={inst.id} hv onClick={()=>onNavigate("detail",inst.id)}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:12}}>
              <div><div style={{fontSize:15,fontWeight:600,color:C.txB}}>{inst.name}</div><div style={{fontSize:11,color:C.txM,marginTop:2,fontFamily:M}}>v{inst.detected_version||"?"}</div></div>
              <Pill status={health}/>
            </div>
            <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:4,padding:"12px 0",borderTop:"1px solid "+C.border}}>
              <Stat l="Trunks" v={`${trunkUp}/${trunks.length}`} c={trunkUp<trunks.length?C.r:C.g}/>
              <Stat l="SBCs" v={`${sbcUp}/${sbcs.length}`} c={sbcUp<sbcs.length?C.r:C.g}/>
              <Stat l="License" v={lic.is_valid?"OK":"--"} c={lic.is_valid?C.g:C.y}/>
              <Stat l="Polled" v={ago(inst.last_poll_at||inst.last_success_at)} c={C.txD}/>
            </div>
            <div style={{fontSize:11,color:C.txM,marginTop:6,fontFamily:M}}>{inst.base_url}</div>
          </Card>;
        })}
      </div>
    </>}

    {/* Backup Status Table */}
    {instances.length>0&&<>
      <div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:10}}>Backup Status</div>
      <Card style={{marginBottom:22}}>
        <Table cols={[
          {k:"name",l:"PBX",r:(v,r)=><span style={{fontWeight:500,color:C.txB}}>{r.pbx_name}</span>},
          {k:"last_backup",l:"Last Backup",r:v=>fTime(v)},
          {k:"age",l:"Age",r:(v,r)=>{
            if(!r.last_backup)return<span style={{color:C.r}}>No backups</span>;
            const h=Math.floor((Date.now()-new Date(r.last_backup).getTime())/3600000);
            return<span style={{color:h>24?C.r:C.g}}>{h<1?"<1h":h+"h"}</span>;
          }},
          {k:"total",l:"Total Backups"},
          {k:"total_size",l:"Total Size",r:v=>fBytes(v)},
        ]} data={instances.map(inst=>{
          const myBackups=(backups||[]).filter(b=>b.pbx_id===inst.id);
          const latest=myBackups[0];
          const totalSize=myBackups.reduce((a,b)=>a+(b.size_bytes||0),0);
          return{id:inst.id,pbx_name:inst.name,last_backup:latest?.downloaded_at||latest?.created_on_pbx,total:myBackups.length,total_size:totalSize};
        })}/>
      </Card>
    </>}

    {/* Recent Alerts */}
    {firingAlerts.length>0&&<>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:10}}>
        <div style={{fontSize:14,fontWeight:600,color:C.txB}}>Recent Alerts</div>
        <Btn small variant="ghost" onClick={()=>onNavigate("alerts")}>View All</Btn>
      </div>
      <Card>
        <Table cols={[
          {k:"severity",l:"Severity",r:v=><Pill status={v}/>},
          {k:"title",l:"Alert",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},
          {k:"pbx_name",l:"PBX"},
          {k:"fired_at",l:"Fired",r:v=>fTime(v)},
        ]} data={firingAlerts.slice(0,5)}/>
      </Card>
    </>}
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   SYSTEMS PAGE (list)
   ═══════════════════════════════════════════════════════════════════════════ */
function SystemsPage({onSelect,onAdd}){
  const[instances,setInstances]=useState([]);
  const[loading,setLoading]=useState(true);
  const[error,setError]=useState("");
  const[deleting,setDeleting]=useState(null);

  const load=useCallback(async()=>{
    try{const data=await api.get("/pbx/instances");setInstances(data||[]);setError("");}
    catch{setError("Failed to load systems");}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{load();},[load]);

  const deleteInst=async(id,name)=>{
    if(!confirm(`Delete system "${name}"? This cannot be undone.`))return;
    setDeleting(id);
    try{await api.del("/pbx/instances/"+id);load();}
    catch{alert("Delete failed");}
    finally{setDeleting(null);}
  };

  if(loading)return<PageLoader/>;

  return<div>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Systems</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{instances.length} PBX system{instances.length!==1?"s":""}</p></div>
      <div style={{display:"flex",gap:8}}><Btn variant="ghost" small onClick={load}><Sv d={iRf} s={14}/> Refresh</Btn><Btn variant="accent" onClick={onAdd}><Sv d={iP} s={14}/> Add System</Btn></div>
    </div>
    {error&&<ErrorMsg msg={error} onRetry={load}/>}
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(360px,1fr))",gap:12}}>
      {instances.map(inst=>{
        const health=inst.consecutive_failures>0?"warning":"healthy";
        return<Card key={inst.id} hv onClick={()=>onSelect(inst.id)}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:12}}>
            <div><div style={{fontSize:15,fontWeight:600,color:C.txB}}>{inst.name}</div><div style={{fontSize:11,color:C.txM,marginTop:2,fontFamily:M}}>v{inst.detected_version||"?"} {inst.is_enabled?"":"(disabled)"}</div></div>
            <div style={{display:"flex",gap:6,alignItems:"center"}}>
              <Pill status={inst.is_enabled?health:"offline"} label={inst.is_enabled?(inst.consecutive_failures>0?"degraded":"healthy"):"disabled"}/>
            </div>
          </div>
          <div style={{fontSize:11,color:C.txM,fontFamily:M,marginBottom:8}}>{inst.base_url}</div>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",fontSize:11,color:C.txM}}>
            <span>Polled {ago(inst.last_poll_at||inst.last_success_at)} ago</span>
            <div style={{display:"flex",gap:4}} onClick={e=>e.stopPropagation()}>
              <Btn small variant="ghost" onClick={()=>deleteInst(inst.id,inst.name)} loading={deleting===inst.id}><Sv d={iTrash} s={13} c={C.r}/></Btn>
            </div>
          </div>
          {inst.last_error&&<div style={{marginTop:6,fontSize:11,color:C.r,fontFamily:M,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{inst.last_error}</div>}
        </Card>;
      })}
    </div>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   SYSTEM DETAIL PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function DetailPage({instanceId,onBack}){
  const[status,setStatus]=useState(null);
  const[loading,setLoading]=useState(true);
  const[error,setError]=useState("");
  const[tab,setTab]=useState("trunks");
  const[polling,setPolling]=useState(false);
  const[showEdit,setShowEdit]=useState(false);
  const[backups,setBackups]=useState([]);

  const load=useCallback(async()=>{
    try{
      const[s,bk]=await Promise.all([
        api.get("/pbx/instances/"+instanceId+"/status"),
        api.get("/backups?pbx_id="+instanceId),
      ]);
      setStatus(s);setBackups(bk||[]);setError("");
    }catch{setError("Failed to load system status");}
    finally{setLoading(false);}
  },[instanceId]);

  useEffect(()=>{load();},[load]);

  const doPoll=async()=>{
    setPolling(true);
    try{await api.post("/pbx/instances/"+instanceId+"/poll");setTimeout(load,3000);}
    catch{alert("Poll failed");}
    finally{setPolling(false);}
  };

  if(loading)return<PageLoader/>;
  if(error)return<><Btn variant="ghost" small onClick={onBack} style={{marginBottom:8}}>Back to Systems</Btn><ErrorMsg msg={error} onRetry={load}/></>;
  if(!status)return<ErrorMsg msg="System not found"/>;

  const pbx=status.pbx||{};
  const trunks=status.trunks||[];
  const sbcs=status.sbcs||[];
  const lic=status.license||{};
  const caps=status.capabilities||[];
  const tabs=[{id:"trunks",l:"Trunks",n:trunks.length},{id:"sbcs",l:"SBCs",n:sbcs.length},{id:"license",l:"License"},{id:"backups",l:"Backups",n:backups.length},{id:"caps",l:"Capabilities",n:caps.length}];

  return<div>
    <Btn variant="ghost" small onClick={onBack} style={{marginBottom:8}}>Back to Systems</Btn>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}>
      <div>
        <h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>{pbx.name}</h1>
        <div style={{fontSize:12,color:C.txM,marginTop:2,fontFamily:M}}>{pbx.base_url} | v{pbx.detected_version||"?"} | poll: {pbx.poll_interval_s}s</div>
      </div>
      <div style={{display:"flex",gap:8,alignItems:"center"}}>
        <Pill status={status.overall_health||"unknown"}/>
        <Btn small variant="default" onClick={doPoll} loading={polling}><Sv d={iRf} s={14}/> Poll Now</Btn>
        <Btn small variant="ghost" onClick={()=>setShowEdit(true)}><Sv d={iEdit} s={14}/> Edit</Btn>
      </div>
    </div>

    {pbx.last_error&&<div style={{marginBottom:12,padding:10,background:C.rB,borderRadius:6,fontSize:12,color:C.r,fontFamily:M}}>Last error: {pbx.last_error}</div>}

    <div style={{display:"flex",gap:0,marginBottom:16,borderBottom:"1px solid "+C.border}}>
      {tabs.map(t=><button key={t.id} onClick={()=>setTab(t.id)} style={{padding:"10px 18px",fontSize:13,fontWeight:tab===t.id?600:400,color:tab===t.id?C.txB:C.txM,background:"transparent",border:"none",borderBottom:tab===t.id?"2px solid "+C.ac:"2px solid transparent",cursor:"pointer",fontFamily:F}}>{t.l}{t.n!=null?` (${t.n})`:""}</button>)}
    </div>

    {tab==="trunks"&&<Card><Table cols={[
      {k:"trunk_name",l:"Trunk",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},
      {k:"status",l:"Status",r:v=><Pill status={v}/>},
      {k:"provider",l:"Provider"},
      {k:"last_error",l:"Last Error",r:v=>v?<span style={{color:C.r,fontSize:12,fontFamily:M}}>{v}</span>:"\u2014"},
      {k:"inbound_enabled",l:"In",r:v=>v?<Sv d={iCk} s={14} c={C.g}/>:<Sv d={iX} s={14} c={C.r}/>},
      {k:"outbound_enabled",l:"Out",r:v=>v?<Sv d={iCk} s={14} c={C.g}/>:<Sv d={iX} s={14} c={C.r}/>},
      {k:"last_status_change",l:"Changed",r:v=><span style={{fontSize:12,fontFamily:M}}>{fTime(v)}</span>},
    ]} data={trunks}/></Card>}

    {tab==="sbcs"&&<Card><Table cols={[
      {k:"sbc_name",l:"SBC",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},
      {k:"status",l:"Status",r:v=><Pill status={v}/>},
      {k:"tunnel_status",l:"Tunnel"},
      {k:"last_seen",l:"Last Seen",r:v=><span style={{fontSize:12,fontFamily:M}}>{fTime(v)}</span>},
    ]} data={sbcs}/></Card>}

    {tab==="license"&&<Card>
      <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:20,marginBottom:16}}>
        {[{l:"Edition",v:lic.edition||"\u2014"},{l:"Expiry",v:fDate(lic.expiry_date),c:lic.is_valid?C.txB:C.r},{l:"Max Calls",v:lic.max_sim_calls||"\u2014"}].map((s,i)=><div key={i}>
          <div style={{fontSize:10,color:C.txM,textTransform:"uppercase",letterSpacing:".05em",marginBottom:4}}>{s.l}</div>
          <div style={{fontSize:18,fontWeight:600,color:s.c||C.txB,fontFamily:M}}>{s.v}</div>
        </div>)}
      </div>
      {lic.warnings?.length>0&&<div style={{padding:12,background:C.yB,border:"1px solid rgba(241,196,15,.15)",borderRadius:6,marginTop:12}}>
        {lic.warnings.map((w,i)=><div key={i} style={{fontSize:13,color:C.y}}>Warning: {w}</div>)}
      </div>}
    </Card>}

    {tab==="backups"&&<Card><Table cols={[
      {k:"filename",l:"File",r:v=><span style={{fontWeight:500,color:C.txB,fontFamily:M,fontSize:12}}>{v}</span>},
      {k:"created_on_pbx",l:"Created on PBX",r:v=>fTime(v)},
      {k:"downloaded_at",l:"Downloaded",r:v=>fTime(v)},
      {k:"size_bytes",l:"Size",r:v=>fBytes(v)},
      {k:"backup_type",l:"Type"},
      {k:"is_downloaded",l:"Local",r:v=>v?<Sv d={iCk} s={14} c={C.g}/>:<Sv d={iX} s={14} c={C.txM}/>},
    ]} data={backups}/></Card>}

    {tab==="caps"&&<Card>
      <div style={{fontSize:12,color:C.txD,marginBottom:12}}>Discovered during connection probe</div>
      <Table cols={[
        {k:"feature",l:"Feature",r:v=><span style={{fontWeight:500,color:C.txB,textTransform:"capitalize"}}>{v.replace(/_/g," ")}</span>},
        {k:"status",l:"Status",r:v=><Pill status={v}/>},
        {k:"method",l:"Method",r:v=><span style={{fontSize:12,fontFamily:M}}>{v||"\u2014"}</span>},
      ]} data={caps}/>
    </Card>}

    {showEdit&&<EditInstanceModal inst={pbx} onClose={()=>setShowEdit(false)} onSave={load}/>}
  </div>;
}


/* ═══════════════════════════════════════════════════════════════════════════
   PHONE NUMBERS PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function PhoneNumbersPage(){
  const[numbers,setNumbers]=useState([]);
  const[summary,setSummary]=useState({});
  const[instances,setInstances]=useState([]);
  const[loading,setLoading]=useState(true);
  const[error,setError]=useState("");
  const[syncing,setSyncing]=useState(null);
  const[showReport,setShowReport]=useState(false);
  const[report,setReport]=useState(null);
  const[filters,setFilters]=useState({pbx:"",trunk:"",type:"",search:""});

  const load=useCallback(async()=>{
    try{
      const[nums,sum,inst]=await Promise.all([
        api.get("/phone-numbers"),
        api.get("/phone-numbers/summary").catch(()=>({})),
        api.get("/pbx/instances"),
      ]);
      setNumbers(nums||[]);setSummary(sum||{});setInstances(inst||[]);setError("");
    }catch{setError("Failed to load phone numbers");}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{load();},[load]);

  const syncPbx=async(pbxId)=>{
    setSyncing(pbxId);
    try{await api.post("/phone-numbers/sync/"+pbxId);setTimeout(load,2000);}
    catch{alert("Sync failed");}
    finally{setSyncing(null);}
  };

  const syncAll=async()=>{
    setSyncing("all");
    try{await api.post("/phone-numbers/sync-all");setTimeout(load,3000);}
    catch{alert("Sync failed");}
    finally{setSyncing(null);}
  };

  const loadReport=async()=>{
    try{const r=await api.get("/phone-numbers/report");setReport(r);setShowReport(true);}
    catch{alert("Failed to generate report");}
  };

  if(loading)return<PageLoader/>;

  const filtered=(numbers||[]).filter(n=>{
    if(filters.pbx&&n.pbx_id!==filters.pbx)return false;
    if(filters.type&&n.number_type!==filters.type)return false;
    if(filters.search){
      const s=filters.search.toLowerCase();
      if(!(n.number||"").toLowerCase().includes(s)&&!(n.display_name||"").toLowerCase().includes(s))return false;
    }
    return true;
  });

  const types=[...new Set((numbers||[]).map(n=>n.number_type).filter(Boolean))];

  return<div>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Phone Numbers</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{summary.total||numbers.length} numbers across {instances.length} systems</p></div>
      <div style={{display:"flex",gap:8}}>
        <Btn small variant="ghost" onClick={loadReport}>Report</Btn>
        <Btn small variant="default" onClick={()=>window.open("/api/phone-numbers/export"+(filters.pbx?"?pbx_id="+filters.pbx:""),"_blank")}>Export CSV</Btn>
        <Btn small variant="default" onClick={syncAll} loading={syncing==="all"}><Sv d={iRf} s={14}/> Sync All</Btn>
      </div>
    </div>
    {error&&<ErrorMsg msg={error} onRetry={load}/>}

    {/* Summary stats */}
    <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10,marginBottom:18}}>
      <Card style={{padding:14,display:"flex",justifyContent:"center"}}><Stat l="Total Numbers" v={summary.total||numbers.length} c={C.b}/></Card>
      <Card style={{padding:14,display:"flex",justifyContent:"center"}}><Stat l="DIDs" v={summary.did_count||(numbers||[]).filter(n=>n.number_type==="did").length} c={C.txB}/></Card>
      <Card style={{padding:14,display:"flex",justifyContent:"center"}}><Stat l="Systems" v={summary.pbx_count||instances.length} c={C.txB}/></Card>
      <Card style={{padding:14,display:"flex",justifyContent:"center"}}><Stat l="Trunks" v={summary.trunk_count||"--"} c={C.txB}/></Card>
    </div>

    {/* Per-PBX sync buttons */}
    {instances.length>0&&<div style={{display:"flex",gap:8,marginBottom:16,flexWrap:"wrap"}}>
      {instances.map(inst=><Btn key={inst.id} small variant="ghost" onClick={()=>syncPbx(inst.id)} loading={syncing===inst.id}><Sv d={iRf} s={12}/> Sync {inst.name}</Btn>)}
    </div>}

    {/* Filters */}
    <Card style={{marginBottom:16,padding:14}}>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr 2fr",gap:12}}>
        <Select label="PBX" value={filters.pbx} onChange={v=>setFilters(p=>({...p,pbx:v}))} options={[{v:"",l:"All Systems"},...instances.map(i=>({v:i.id,l:i.name}))]}/>
        <Select label="Type" value={filters.type} onChange={v=>setFilters(p=>({...p,type:v}))} options={[{v:"",l:"All Types"},...types.map(t=>({v:t,l:t.toUpperCase()}))]}/>
        <div/>
        <Input label="Search" value={filters.search} onChange={v=>setFilters(p=>({...p,search:v}))} placeholder="Search number or name..."/>
      </div>
    </Card>

    <Card>
      <Table cols={[
        {k:"number",l:"Phone Number",r:v=><span style={{fontWeight:600,color:C.txB,fontFamily:M}}>{v}</span>},
        {k:"display_name",l:"Display Name"},
        {k:"pbx_name",l:"PBX",r:(v,r)=>{const inst=instances.find(i=>i.id===r.pbx_id);return inst?.name||r.pbx_id;}},
        {k:"trunk_name",l:"Trunk"},
        {k:"number_type",l:"Type",r:v=><Pill status={v==="did"?"info":"skip"} label={v||"--"}/>},
        {k:"inbound_route",l:"Inbound Route"},
        {k:"outbound_cid",l:"Outbound CID",r:v=>v?<Sv d={iCk} s={14} c={C.g}/>:<Sv d={iX} s={14} c={C.txM}/>},
      ]} data={filtered}/>
    </Card>

    {showReport&&report&&<Modal onClose={()=>setShowReport(false)} title="Phone Number Report" width={700}>
      <div style={{fontSize:13,color:C.txD,whiteSpace:"pre-wrap",fontFamily:M,maxHeight:500,overflow:"auto"}}>
        {typeof report==="string"?report:JSON.stringify(report,null,2)}
      </div>
      <div style={{display:"flex",justifyContent:"flex-end",marginTop:16}}><Btn variant="ghost" onClick={()=>setShowReport(false)}>Close</Btn></div>
    </Modal>}
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   BACKUPS PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function BackupsPage(){
  const[backups,setBackups]=useState([]);
  const[instances,setInstances]=useState([]);
  const[schedules,setSchedules]=useState({});
  const[loading,setLoading]=useState(true);
  const[error,setError]=useState("");
  const[actionLoading,setActionLoading]=useState(null);
  const[editSchedule,setEditSchedule]=useState(null);

  const load=useCallback(async()=>{
    try{
      const[bk,inst]=await Promise.all([
        api.get("/backups?limit=200"),
        api.get("/pbx/instances"),
      ]);
      setBackups(bk||[]);setInstances(inst||[]);
      // Load schedules for each PBX
      const sMap={};
      await Promise.all((inst||[]).map(async(i)=>{
        try{const s=await api.get("/backups/"+i.id+"/schedule");sMap[i.id]=s;}catch{}
      }));
      setSchedules(sMap);
      setError("");
    }catch{setError("Failed to load backups");}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{load();},[load]);

  const pullLatest=async(pbxId)=>{
    setActionLoading("pull-"+pbxId);
    try{await api.post("/backups/"+pbxId+"/pull");setTimeout(load,3000);}
    catch{alert("Pull failed");}
    finally{setActionLoading(null);}
  };
  const triggerBackup=async(pbxId)=>{
    setActionLoading("trigger-"+pbxId);
    try{await api.post("/backups/"+pbxId+"/trigger");setTimeout(load,5000);}
    catch{alert("Trigger failed");}
    finally{setActionLoading(null);}
  };

  if(loading)return<PageLoader/>;

  const pbxMap=Object.fromEntries(instances.map(i=>[i.id,i.name]));

  return<div>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Backups</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{backups.length} backups across {instances.length} systems</p></div>
      <Btn variant="ghost" small onClick={load}><Sv d={iRf} s={14}/> Refresh</Btn>
    </div>
    {error&&<ErrorMsg msg={error} onRetry={load}/>}

    {/* Per-PBX Status Cards */}
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(320px,1fr))",gap:12,marginBottom:22}}>
      {instances.map(inst=>{
        const myBackups=backups.filter(b=>b.pbx_id===inst.id);
        const latest=myBackups[0];
        const sched=schedules[inst.id]||{};
        const latestDate=latest?.downloaded_at||latest?.created_on_pbx;
        const ageH=latestDate?Math.floor((Date.now()-new Date(latestDate).getTime())/3600000):null;
        return<Card key={inst.id}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:10}}>
            <div><div style={{fontSize:14,fontWeight:600,color:C.txB}}>{inst.name}</div><div style={{fontSize:11,color:C.txM,marginTop:2}}>{myBackups.length} backups</div></div>
            <Pill status={ageH===null?"warning":ageH>24?"error":"healthy"} label={ageH===null?"No backups":ageH>24?"Stale":"OK"}/>
          </div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,fontSize:12,color:C.txD,marginBottom:10}}>
            <div><span style={{color:C.txM}}>Last:</span> {fTime(latestDate)}</div>
            <div><span style={{color:C.txM}}>Size:</span> {fBytes(latest?.size_bytes)}</div>
            <div><span style={{color:C.txM}}>Schedule:</span> {sched.exists?sched.cron_expr:"None"}</div>
            <div><span style={{color:C.txM}}>Next:</span> {sched.next_run_at?fTime(sched.next_run_at):"\u2014"}</div>
          </div>
          <div style={{display:"flex",gap:6}}>
            <Btn small variant="primary" onClick={()=>pullLatest(inst.id)} loading={actionLoading==="pull-"+inst.id}><Sv d={iDl} s={12}/> Pull Latest</Btn>
            <Btn small variant="default" onClick={()=>triggerBackup(inst.id)} loading={actionLoading==="trigger-"+inst.id}>Trigger Backup</Btn>
            <Btn small variant="ghost" onClick={()=>setEditSchedule(inst.id)}>Schedule</Btn>
          </div>
        </Card>;
      })}
    </div>

    {/* All Backups Table */}
    <div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:10}}>All Backups</div>
    <Card>
      <Table cols={[
        {k:"pbx_id",l:"PBX",r:v=><span style={{fontWeight:500,color:C.txB}}>{pbxMap[v]||v}</span>},
        {k:"filename",l:"File",r:v=><span style={{fontFamily:M,fontSize:12}}>{v}</span>},
        {k:"created_on_pbx",l:"Created",r:v=>fTime(v)},
        {k:"downloaded_at",l:"Downloaded",r:v=>fTime(v)},
        {k:"size_bytes",l:"Size",r:v=>fBytes(v)},
        {k:"backup_type",l:"Type"},
        {k:"is_downloaded",l:"Local",r:v=>v?<Pill status="pass" label="Yes"/>:<Pill status="skip" label="No"/>},
      ]} data={backups}/>
    </Card>

    {/* Schedule Edit Modal */}
    {editSchedule&&<BackupScheduleModal pbxId={editSchedule} current={schedules[editSchedule]} onClose={()=>setEditSchedule(null)} onSave={load}/>}
  </div>;
}

function BackupScheduleModal({pbxId,current,onClose,onSave}){
  const[form,setForm]=useState({
    cron_expr:current?.cron_expr||"0 2 * * *",
    retain_count:current?.retain_count||10,
    retain_days:current?.retain_days||90,
    encrypt_at_rest:current?.encrypt_at_rest||false,
    is_enabled:current?.is_enabled!==false,
  });
  const[saving,setSaving]=useState(false);
  const upd=(k,v)=>setForm(p=>({...p,[k]:v}));

  const save=async()=>{
    setSaving(true);
    try{
      await api.put("/backups/"+pbxId+"/schedule",form);
      onSave();onClose();
    }catch(err){
      let msg="Save failed";try{const b=await err.json();msg=b.detail||msg;}catch{}
      alert(msg);
    }finally{setSaving(false);}
  };

  return<Modal onClose={onClose} title="Backup Schedule" subtitle="Configure automatic backup schedule">
    <Input label="Cron Expression" value={form.cron_expr} onChange={v=>upd("cron_expr",v)} mono placeholder="0 2 * * *" help="Standard cron format: minute hour day month weekday"/>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Input label="Retain Count" value={form.retain_count} onChange={v=>upd("retain_count",parseInt(v)||0)} type="number" help="Keep last N backups"/>
      <Input label="Retain Days" value={form.retain_days} onChange={v=>upd("retain_days",parseInt(v)||0)} type="number" help="Delete backups older than N days"/>
    </div>
    <div style={{marginBottom:16,display:"flex",gap:16}}>
      <label style={{display:"flex",alignItems:"center",gap:8,cursor:"pointer"}}><input type="checkbox" checked={form.is_enabled} onChange={e=>upd("is_enabled",e.target.checked)} style={{accentColor:C.ac}}/><span style={{fontSize:13,color:C.txB}}>Enabled</span></label>
      <label style={{display:"flex",alignItems:"center",gap:8,cursor:"pointer"}}><input type="checkbox" checked={form.encrypt_at_rest} onChange={e=>upd("encrypt_at_rest",e.target.checked)} style={{accentColor:C.ac}}/><span style={{fontSize:13,color:C.txB}}>Encrypt at Rest</span></label>
    </div>
    <div style={{display:"flex",justifyContent:"flex-end",gap:10,paddingTop:12,borderTop:"1px solid "+C.border}}>
      <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
      <Btn variant="primary" onClick={save} loading={saving}>Save Schedule</Btn>
    </div>
  </Modal>;
}


/* ═══════════════════════════════════════════════════════════════════════════
   ALERTS PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function AlertsPage(){
  const[alerts,setAlerts]=useState([]);
  const[instances,setInstances]=useState([]);
  const[loading,setLoading]=useState(true);
  const[error,setError]=useState("");
  const[stateFilter,setStateFilter]=useState("");
  const[pbxFilter,setPbxFilter]=useState("");
  const[acking,setAcking]=useState(null);

  const load=useCallback(async()=>{
    try{
      let url="/alerts?limit=200";
      if(stateFilter)url+="&state="+stateFilter;
      if(pbxFilter)url+="&pbx_id="+pbxFilter;
      const[al,inst]=await Promise.all([api.get(url),api.get("/pbx/instances")]);
      setAlerts(al||[]);setInstances(inst||[]);setError("");
    }catch{setError("Failed to load alerts");}
    finally{setLoading(false);}
  },[stateFilter,pbxFilter]);

  useEffect(()=>{load();},[load]);

  const ack=async(id)=>{
    setAcking(id);
    try{await api.post("/alerts/"+id+"/acknowledge");load();}
    catch{alert("Acknowledge failed");}
    finally{setAcking(null);}
  };

  const firingCount=(alerts||[]).filter(a=>a.state==="firing").length;

  return<div>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Alerts</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{firingCount} firing, {alerts.length} total</p></div>
      <Btn variant="ghost" small onClick={load}><Sv d={iRf} s={14}/> Refresh</Btn>
    </div>
    {error&&<ErrorMsg msg={error} onRetry={load}/>}

    {/* Filters */}
    <Card style={{marginBottom:16,padding:14}}>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 2fr",gap:12}}>
        <Select label="State" value={stateFilter} onChange={v=>{setStateFilter(v);setLoading(true);}} options={[{v:"",l:"All States"},{v:"firing",l:"Firing"},{v:"acknowledged",l:"Acknowledged"},{v:"resolved",l:"Resolved"}]}/>
        <Select label="PBX" value={pbxFilter} onChange={v=>{setPbxFilter(v);setLoading(true);}} options={[{v:"",l:"All Systems"},...instances.map(i=>({v:i.id,l:i.name}))]}/>
        <div/>
      </div>
    </Card>

    {loading?<PageLoader/>:<Card>
      <Table cols={[
        {k:"severity",l:"Severity",r:v=><Pill status={v}/>},
        {k:"state",l:"State",r:v=><Pill status={v}/>},
        {k:"title",l:"Alert",r:v=><span style={{fontWeight:500,color:C.txB}}>{v}</span>},
        {k:"pbx_name",l:"PBX"},
        {k:"fired_at",l:"Fired",r:v=><span style={{fontSize:12,fontFamily:M}}>{fTime(v)}</span>},
        {k:"resolved_at",l:"Resolved",r:v=>v?<span style={{fontSize:12,fontFamily:M}}>{fTime(v)}</span>:"\u2014"},
        {k:"id",l:"",r:(v,r)=>r.state==="firing"?<Btn small variant="ghost" onClick={()=>ack(v)} loading={acking===v}>Ack</Btn>:null},
      ]} data={alerts}/>
    </Card>}
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   AUDIT LOG PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function AuditPage(){
  const[entries,setEntries]=useState([]);
  const[total,setTotal]=useState(0);
  const[loading,setLoading]=useState(true);
  const[error,setError]=useState("");
  const[offset,setOffset]=useState(0);
  const[filters,setFilters]=useState({action:"",target_type:"",success:""});
  const limit=50;

  const load=useCallback(async()=>{
    try{
      let url=`/audit?limit=${limit}&offset=${offset}`;
      if(filters.action)url+="&action="+filters.action;
      if(filters.target_type)url+="&target_type="+filters.target_type;
      if(filters.success!=="")url+="&success="+filters.success;
      const res=await api.get(url);
      setEntries(res.entries||[]);setTotal(res.total||0);setError("");
    }catch{setError("Failed to load audit log");}
    finally{setLoading(false);}
  },[offset,filters]);

  useEffect(()=>{load();},[load]);

  const exportCsv=()=>{
    let url="/api/audit/export?";
    if(filters.action)url+="action="+filters.action+"&";
    if(filters.target_type)url+="target_type="+filters.target_type+"&";
    window.open(url,"_blank");
  };

  const totalPages=Math.ceil(total/limit);
  const currentPage=Math.floor(offset/limit)+1;

  return<div>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Audit Log</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{total} entries</p></div>
      <div style={{display:"flex",gap:8}}><Btn small onClick={exportCsv}>Export CSV</Btn><Btn variant="ghost" small onClick={()=>{setOffset(0);setLoading(true);}}><Sv d={iRf} s={14}/> Refresh</Btn></div>
    </div>
    {error&&<ErrorMsg msg={error} onRetry={load}/>}

    {/* Filters */}
    <Card style={{marginBottom:16,padding:14}}>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12}}>
        <Input label="Action" value={filters.action} onChange={v=>{setFilters(p=>({...p,action:v}));setOffset(0);setLoading(true);}} placeholder="e.g. user_login"/>
        <Input label="Target Type" value={filters.target_type} onChange={v=>{setFilters(p=>({...p,target_type:v}));setOffset(0);setLoading(true);}} placeholder="e.g. pbx, user"/>
        <Select label="Result" value={filters.success} onChange={v=>{setFilters(p=>({...p,success:v}));setOffset(0);setLoading(true);}} options={[{v:"",l:"All"},{v:"true",l:"Success"},{v:"false",l:"Failed"}]}/>
      </div>
    </Card>

    {loading?<PageLoader/>:<Card>
      <Table cols={[
        {k:"created_at",l:"Time",r:v=><span style={{fontSize:12,fontFamily:M}}>{fTime(v)}</span>},
        {k:"action",l:"Action",r:v=><span style={{fontSize:12,fontFamily:M,color:C.ac}}>{v}</span>},
        {k:"username",l:"User",r:v=><span style={{fontWeight:500,color:C.txB}}>{v||"system"}</span>},
        {k:"target_type",l:"Target Type"},
        {k:"target_name",l:"Target"},
        {k:"detail",l:"Detail",r:v=>{if(!v||typeof v==="object"&&Object.keys(v).length===0)return"\u2014";return<span style={{fontSize:11,fontFamily:M,color:C.txD}}>{typeof v==="object"?JSON.stringify(v):String(v)}</span>}},
        {k:"success",l:"Result",r:v=>v?<Pill status="pass" label="OK"/>:<Pill status="fail" label="FAIL"/>},
        {k:"ip_address",l:"IP",r:v=><span style={{fontSize:11,fontFamily:M,color:C.txM}}>{v||"\u2014"}</span>},
      ]} data={entries}/>

      {/* Pagination */}
      {totalPages>1&&<div style={{display:"flex",justifyContent:"center",alignItems:"center",gap:12,padding:"16px 0",borderTop:"1px solid "+C.border,marginTop:8}}>
        <Btn small variant="ghost" disabled={offset===0} onClick={()=>{setOffset(Math.max(0,offset-limit));setLoading(true);}}>Previous</Btn>
        <span style={{fontSize:12,color:C.txM}}>Page {currentPage} of {totalPages}</span>
        <Btn small variant="ghost" disabled={currentPage>=totalPages} onClick={()=>{setOffset(offset+limit);setLoading(true);}}>Next</Btn>
      </div>}
    </Card>}
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   USERS PAGE (admin only)
   ═══════════════════════════════════════════════════════════════════════════ */
function UsersPage(){
  const[users,setUsers]=useState([]);
  const[loading,setLoading]=useState(true);
  const[error,setError]=useState("");
  const[showAdd,setShowAdd]=useState(false);
  const[editUser,setEditUser]=useState(null);

  const load=useCallback(async()=>{
    try{const data=await api.get("/users");setUsers(data||[]);setError("");}
    catch{setError("Failed to load users");}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{load();},[load]);

  const toggleActive=async(user)=>{
    try{
      await api.patch("/users/"+user.id,{is_active:!user.is_active});
      load();
    }catch{alert("Update failed");}
  };

  const resetPassword=async(user)=>{
    const newPw=prompt(`Enter new password for ${user.username}:`);
    if(!newPw)return;
    try{
      await api.patch("/users/"+user.id,{password:newPw});
      alert("Password reset successfully");
    }catch{alert("Password reset failed");}
  };

  if(loading)return<PageLoader/>;

  return<div>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}>
      <div><h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:0}}>Users</h1><p style={{fontSize:13,color:C.txM,margin:"3px 0 0"}}>{users.length} users</p></div>
      <div style={{display:"flex",gap:8}}><Btn variant="ghost" small onClick={load}><Sv d={iRf} s={14}/></Btn><Btn variant="accent" onClick={()=>setShowAdd(true)}><Sv d={iP} s={14}/> Add User</Btn></div>
    </div>
    {error&&<ErrorMsg msg={error} onRetry={load}/>}

    <Card>
      <Table cols={[
        {k:"username",l:"Username",r:v=><span style={{fontWeight:600,color:C.txB}}>{v}</span>},
        {k:"email",l:"Email"},
        {k:"display_name",l:"Display Name"},
        {k:"role",l:"Role",r:v=><Pill status={v} label={v}/>},
        {k:"auth_method",l:"Auth",r:v=><Pill status={v} label={v==="azure_ad"?"Azure AD":"Local"}/>},
        {k:"is_active",l:"Status",r:v=><Pill status={v?"active":"inactive"} label={v?"Active":"Inactive"}/>},
        {k:"last_login",l:"Last Login",r:v=>v?<span style={{fontSize:12,fontFamily:M}}>{fTime(v)}</span>:"\u2014"},
        {k:"id",l:"Actions",r:(v,r)=><div style={{display:"flex",gap:4}}>
          <Btn small variant="ghost" onClick={()=>setEditUser(r)}><Sv d={iEdit} s={13}/></Btn>
          <Btn small variant="ghost" onClick={()=>toggleActive(r)}>{r.is_active?"Deactivate":"Activate"}</Btn>
          {r.auth_method==="local"&&<Btn small variant="ghost" onClick={()=>resetPassword(r)}>Reset PW</Btn>}
        </div>},
      ]} data={users}/>
    </Card>

    {showAdd&&<AddUserModal onClose={()=>setShowAdd(false)} onSave={()=>{setShowAdd(false);load();}}/>}
    {editUser&&<EditUserModal user={editUser} onClose={()=>setEditUser(null)} onSave={()=>{setEditUser(null);load();}}/>}
  </div>;
}

function AddUserModal({onClose,onSave}){
  const[form,setForm]=useState({username:"",email:"",password:"",role:"viewer",display_name:""});
  const[saving,setSaving]=useState(false);
  const[error,setError]=useState("");
  const upd=(k,v)=>setForm(p=>({...p,[k]:v}));

  const save=async()=>{
    if(!form.username||!form.password){setError("Username and password required");return;}
    setSaving(true);setError("");
    try{await api.post("/users",form);onSave();}
    catch(err){let msg="Failed to create user";try{const b=await err.json();msg=b.detail||msg;}catch{}setError(msg);}
    finally{setSaving(false);}
  };

  return<Modal onClose={onClose} title="Add User" subtitle="Create a new user account">
    <Input label="Username" value={form.username} onChange={v=>upd("username",v)} required/>
    <Input label="Email" value={form.email} onChange={v=>upd("email",v)} placeholder="user@example.com"/>
    <Input label="Display Name" value={form.display_name} onChange={v=>upd("display_name",v)}/>
    <Input label="Password" value={form.password} onChange={v=>upd("password",v)} type="password" required/>
    <Select label="Role" value={form.role} onChange={v=>upd("role",v)} options={[{v:"viewer",l:"Viewer"},{v:"operator",l:"Operator"},{v:"admin",l:"Admin"}]}/>
    {error&&<div style={{fontSize:12,color:C.r,marginBottom:12}}>{error}</div>}
    <div style={{display:"flex",justifyContent:"flex-end",gap:10,paddingTop:12,borderTop:"1px solid "+C.border}}>
      <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
      <Btn variant="primary" onClick={save} loading={saving}>Create User</Btn>
    </div>
  </Modal>;
}

function EditUserModal({user,onClose,onSave}){
  const[form,setForm]=useState({email:user.email||"",display_name:user.display_name||"",role:user.role||"viewer"});
  const[saving,setSaving]=useState(false);
  const upd=(k,v)=>setForm(p=>({...p,[k]:v}));

  const save=async()=>{
    setSaving(true);
    try{await api.patch("/users/"+user.id,form);onSave();}
    catch{alert("Update failed");}
    finally{setSaving(false);}
  };

  return<Modal onClose={onClose} title="Edit User" subtitle={user.username}>
    <Input label="Email" value={form.email} onChange={v=>upd("email",v)}/>
    <Input label="Display Name" value={form.display_name} onChange={v=>upd("display_name",v)}/>
    <Select label="Role" value={form.role} onChange={v=>upd("role",v)} options={[{v:"viewer",l:"Viewer"},{v:"operator",l:"Operator"},{v:"admin",l:"Admin"}]}/>
    <div style={{display:"flex",justifyContent:"flex-end",gap:10,paddingTop:12,borderTop:"1px solid "+C.border}}>
      <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
      <Btn variant="primary" onClick={save} loading={saving}>Save</Btn>
    </div>
  </Modal>;
}


/* ═══════════════════════════════════════════════════════════════════════════
   SETTINGS PAGE
   ═══════════════════════════════════════════════════════════════════════════ */
function SettingsPage(){
  const user=JSON.parse(localStorage.getItem("user")||"{}");
  const isAdmin=user.role==="admin";
  const[ssoConfig,setSsoConfig]=useState(null);
  const[ssoForm,setSsoForm]=useState({tenant_id:"",client_id:"",client_secret:"",redirect_uri:"",auto_create_users:true,default_role:"viewer"});
  const[savingSso,setSavingSso]=useState(false);

  useEffect(()=>{
    if(isAdmin){
      api.get("/auth/sso/config").then(d=>{
        setSsoConfig(d);
        if(d){setSsoForm({
          tenant_id:d.tenant_id||"",client_id:d.client_id||"",
          client_secret:"",redirect_uri:d.redirect_uri||"",
          auto_create_users:d.auto_create_users!==false,default_role:d.default_role||"viewer",
        });}
      }).catch(()=>{});
    }
  },[isAdmin]);

  const saveSso=async()=>{
    setSavingSso(true);
    try{await api.put("/auth/sso/config",ssoForm);alert("SSO configuration saved");}
    catch{alert("Save failed");}
    finally{setSavingSso(false);}
  };

  return<div>
    <h1 style={{fontSize:22,fontWeight:700,color:C.txB,margin:"0 0 20px"}}>Settings</h1>
    <div style={{display:"grid",gap:12}}>
      {/* Current User */}
      <Card>
        <div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:12}}>Current User</div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,fontSize:13,color:C.txD}}>
          <div><span style={{color:C.txM}}>Username:</span> {user.username||"\u2014"}</div>
          <div><span style={{color:C.txM}}>Role:</span> <Pill status={user.role||"viewer"} label={user.role||"viewer"}/></div>
        </div>
      </Card>

      {/* Security */}
      <Card>
        <div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:12}}>Security</div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,fontSize:13,color:C.txD}}>
          <div><span style={{color:C.txM}}>Encryption:</span> AES-256-GCM</div>
          <div><span style={{color:C.txM}}>Key source:</span> MASTER_KEY env var</div>
          <div><span style={{color:C.txM}}>JWT expiry:</span> 60 min</div>
          <div><span style={{color:C.txM}}>Login lockout:</span> 5 attempts / 15 min</div>
        </div>
      </Card>

      {/* Polling */}
      <Card>
        <div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:12}}>Polling</div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,fontSize:13,color:C.txD}}>
          <div><span style={{color:C.txM}}>Default interval:</span> 60s</div>
          <div><span style={{color:C.txM}}>Max backoff:</span> 600s</div>
          <div><span style={{color:C.txM}}>Alert check:</span> 30s</div>
          <div><span style={{color:C.txM}}>Capability reprobe:</span> Weekly</div>
        </div>
      </Card>

      {/* Database */}
      <Card>
        <div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:12}}>Database</div>
        <div style={{fontSize:13,color:C.txD}}>
          <div style={{fontFamily:M,fontSize:12,color:C.txM}}>PostgreSQL 16 | Audit log: immutable (trigger-protected) | Poll history: 90-day retention</div>
        </div>
      </Card>

      {/* Azure AD SSO (admin only) */}
      {isAdmin&&<Card>
        <div style={{fontSize:14,fontWeight:600,color:C.txB,marginBottom:4}}>Azure AD SSO</div>
        <div style={{fontSize:12,color:C.txM,marginBottom:16}}>Configure Microsoft Azure Active Directory single sign-on</div>
        <Input label="Tenant ID" value={ssoForm.tenant_id} onChange={v=>setSsoForm(p=>({...p,tenant_id:v}))} mono placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"/>
        <Input label="Client ID" value={ssoForm.client_id} onChange={v=>setSsoForm(p=>({...p,client_id:v}))} mono placeholder="Application (client) ID"/>
        <Input label="Client Secret" value={ssoForm.client_secret} onChange={v=>setSsoForm(p=>({...p,client_secret:v}))} type="password" placeholder="Leave blank to keep current"/>
        <Input label="Redirect URI" value={ssoForm.redirect_uri} onChange={v=>setSsoForm(p=>({...p,redirect_uri:v}))} mono placeholder="https://your-domain.com/api/auth/sso/callback"/>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
          <div style={{marginBottom:16}}><label style={{display:"flex",alignItems:"center",gap:8,cursor:"pointer"}}><input type="checkbox" checked={ssoForm.auto_create_users} onChange={e=>setSsoForm(p=>({...p,auto_create_users:e.target.checked}))} style={{accentColor:C.ac}}/><span style={{fontSize:13,color:C.txB}}>Auto-create users on first SSO login</span></label></div>
          <Select label="Default SSO Role" value={ssoForm.default_role} onChange={v=>setSsoForm(p=>({...p,default_role:v}))} options={[{v:"viewer",l:"Viewer"},{v:"operator",l:"Operator"},{v:"admin",l:"Admin"}]}/>
        </div>
        <div style={{display:"flex",justifyContent:"flex-end",paddingTop:8,borderTop:"1px solid "+C.border}}>
          <Btn variant="primary" onClick={saveSso} loading={savingSso}>Save SSO Config</Btn>
        </div>
      </Card>}
    </div>
  </div>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   APP SHELL
   ═══════════════════════════════════════════════════════════════════════════ */
export default function App(){
  const[authed,setAuthed]=useState(!!localStorage.getItem("token"));
  const[user,setUser]=useState(()=>{try{return JSON.parse(localStorage.getItem("user")||"null")}catch{return null}});
  const[page,setPage]=useState("dashboard");
  const[detailId,setDetailId]=useState(null);
  const[showAdd,setShowAdd]=useState(false);
  const[alertCount,setAlertCount]=useState(0);

  // Listen for auth-logout events from 401 handler
  useEffect(()=>{
    const handler=()=>{setAuthed(false);setUser(null);};
    window.addEventListener("auth-logout",handler);
    return()=>window.removeEventListener("auth-logout",handler);
  },[]);

  // Periodically check firing alert count for badge
  useEffect(()=>{
    if(!authed)return;
    const loadAlertCount=()=>{
      api.get("/alerts?state=firing&limit=1").then(data=>{
        setAlertCount(Array.isArray(data)?data.length:0);
      }).catch(()=>{});
    };
    loadAlertCount();
    const iv=setInterval(loadAlertCount,30000);
    return()=>clearInterval(iv);
  },[authed]);

  const handleLogin=(u)=>{setAuthed(true);setUser(u);};
  const handleLogout=()=>{
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    setAuthed(false);setUser(null);setPage("dashboard");setDetailId(null);
  };

  const navigate=(pg,id)=>{
    if(pg==="detail"&&id){setPage("systems");setDetailId(id);}
    else{setPage(pg);setDetailId(null);}
  };

  if(!authed)return<LoginPage onLogin={handleLogin}/>;

  const isAdmin=user?.role==="admin";

  const nav=[
    {id:"dashboard",l:"Dashboard",d:"M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0v-4a1 1 0 011-1h2a1 1 0 011 1v4"},
    {id:"systems",l:"Systems",d:"M4 6h16M4 6a2 2 0 012-2h12a2 2 0 012 2M4 6v4a2 2 0 002 2h12a2 2 0 002-2V6M6 8h.01M6 16h.01M4 14h16v4a2 2 0 01-2 2H6a2 2 0 01-2-2v-4"},
    {id:"phones",l:"Phone Numbers",d:iPhone},
    {id:"backups",l:"Backups",d:iDl},
    {id:"alerts",l:"Alerts",d:"M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6 6 0 00-5-5.917V4a1 1 0 10-2 0v1.083A6 6 0 006 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0a3 3 0 11-6 0"},
    {id:"audit",l:"Audit Log",d:"M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"},
    ...(isAdmin?[{id:"users",l:"Users",d:iUser}]:[]),
    {id:"settings",l:"Settings",d:"M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z"},
  ];

  const renderPage=()=>{
    if(detailId)return<DetailPage instanceId={detailId} onBack={()=>setDetailId(null)}/>;
    switch(page){
      case"dashboard":return<DashboardPage onNavigate={navigate}/>;
      case"systems":return<SystemsPage onSelect={id=>setDetailId(id)} onAdd={()=>setShowAdd(true)}/>;
      case"phones":return<PhoneNumbersPage/>;
      case"backups":return<BackupsPage/>;
      case"alerts":return<AlertsPage/>;
      case"audit":return<AuditPage/>;
      case"users":return isAdmin?<UsersPage/>:<DashboardPage onNavigate={navigate}/>;
      case"settings":return<SettingsPage/>;
      default:return<DashboardPage onNavigate={navigate}/>;
    }
  };

  return<div style={{display:"flex",height:"100vh",background:C.bg0,color:C.tx,fontFamily:F,fontSize:14}}>
    <nav style={{width:210,background:C.bg1,borderRight:"1px solid "+C.border,display:"flex",flexDirection:"column",padding:"14px 0",flexShrink:0}}>
      <div style={{padding:"2px 18px 18px",borderBottom:"1px solid "+C.border,marginBottom:6}}>
        <div style={{fontSize:16,fontWeight:800,color:C.txB,letterSpacing:"-.02em"}}>PBXMonitor<span style={{color:C.ac}}>X</span></div>
        <div style={{fontSize:10,color:C.txM,marginTop:2,fontFamily:M}}>3CX v20 | {user?.username||"user"}</div>
      </div>
      {nav.map(n=>{const active=(page===n.id&&!detailId)||(n.id==="systems"&&detailId);return<button key={n.id} onClick={()=>{setPage(n.id);setDetailId(null)}} style={{display:"flex",alignItems:"center",gap:10,padding:"9px 18px",margin:"1px 8px",borderRadius:6,border:"none",cursor:"pointer",fontFamily:F,fontSize:13,fontWeight:active?600:400,color:active?C.txB:C.txD,background:active?C.acBg:"transparent",transition:"all .12s",textAlign:"left",position:"relative"}}>
        <Sv d={n.d} s={16} c={active?C.ac:C.txD}/>{n.l}
        {n.id==="alerts"&&alertCount>0&&<span style={{position:"absolute",right:12,background:C.r,color:"#fff",fontSize:9,fontWeight:700,padding:"1px 5px",borderRadius:99,minWidth:16,textAlign:"center"}}>{alertCount}</span>}
      </button>})}
      <div style={{flex:1}}/>
      <button onClick={handleLogout} style={{display:"flex",alignItems:"center",gap:10,padding:"9px 18px",margin:"1px 8px",borderRadius:6,border:"none",cursor:"pointer",fontFamily:F,fontSize:13,fontWeight:400,color:C.txD,background:"transparent",textAlign:"left"}}>
        <Sv d={iLogout} s={16} c={C.txD}/> Logout
      </button>
      <div style={{padding:"10px 18px",borderTop:"1px solid "+C.border,fontSize:10,color:C.txM,fontFamily:M}}>v0.1.0 | <span style={{color:C.g}}>●</span> Connected</div>
    </nav>
    <main style={{flex:1,overflow:"auto",padding:"24px 32px"}}>{renderPage()}</main>
    {showAdd&&<AddInstanceModal onClose={()=>setShowAdd(false)} onSave={()=>{setShowAdd(false);if(page==="systems")setPage("systems");}}/>}
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
      select{-webkit-appearance:auto}
    `}</style>
  </div>;
}
