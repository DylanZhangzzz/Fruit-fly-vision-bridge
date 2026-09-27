// Persistent bridge to the separately installed, unchanged BrainCPU engine.
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import crypto from 'node:crypto';
import readline from 'node:readline';
import {pathToFileURL} from 'node:url';

const modelDir=path.resolve(process.argv[2]);
const {BrainCPU,PARAMETERS}=await import(pathToFileURL(path.join(modelDir,'src/brain.js')).href);
const dir=path.join(modelDir,'public/data');
const manifestBytes=fs.readFileSync(path.join(dir,'manifest.json'));
const manifest=JSON.parse(manifestBytes);
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
function localFile(name){
  const p=path.resolve(dir,name);
  if(!p.startsWith(dir+path.sep))throw Error('Model path escapes data directory');
  return p;
}
const metadataBytes=fs.readFileSync(localFile(manifest.metadata));
const neurons=JSON.parse(zlib.gunzipSync(metadataBytes));
if(neurons.length!==manifest.neurons)throw Error('Neuron metadata length mismatch');
const graph={n:manifest.neurons,neurons,sign:Int32Array.from(neurons,r=>['dopamine','octopamine','serotonin'].includes(r[4])?1:r[5])};
for(const a of manifest.arrays){
  if(!['offsets','sources','counts'].includes(a.name))throw Error('Unexpected graph array');
  const values=new Uint32Array(a.length);let offset=0;
  for(const part of a.parts){
    const compressed=fs.readFileSync(localFile(part.file));
    if(sha(compressed)!==part.sha256)throw Error('Model chunk checksum failed: '+part.file);
    const b=zlib.gunzipSync(compressed);
    if(b.byteLength%4)throw Error('Invalid uint32 chunk');
    const chunk=new Uint32Array(b.buffer,b.byteOffset,b.byteLength/4);
    values.set(chunk,offset);offset+=chunk.length;
  }
  if(offset!==a.length)throw Error('Graph array length mismatch');
  graph[a.name]=values;
}
if(graph.offsets.length!==graph.n+1 || graph.sources.length!==graph.counts.length || graph.sources.length!==manifest.edges)throw Error('Invalid graph dimensions');
const byId=new Map(neurons.map((r,i)=>[String(r[0]),i]));
const brain=new BrainCPU(graph,{seed:1});
const rates=new Float32Array(graph.n);
const send=value=>process.stdout.write(JSON.stringify(value)+'\n');
send({event:'ready',neurons:graph.n,edges:graph.sources.length,dt_ms:PARAMETERS.dt,
  model:'Unmodified Xenova BrainCPU',manifest_sha256:sha(manifestBytes),metadata_sha256:sha(metadataBytes),
  engine_sha256:sha(fs.readFileSync(path.join(modelDir,'src/brain.js')))});

function input(channels){
  // Validate the whole command before changing model state or clearing old rates.
  if(!Array.isArray(channels))throw Error('channels must be an array');
  const seen=new Set(),pairs=[];
  for(const c of channels){
    const id=String(c.bodyId),i=byId.get(id);
    if(seen.has(id))throw Error('Duplicate input body ID');seen.add(id);
    if(i===undefined || neurons[i][1]!=='L2' || neurons[i][3]!=='R')throw Error('Input must identify a right-eye L2: '+id);
    if(!Number.isFinite(c.rate_hz)||c.rate_hz<0||c.rate_hz>120)throw Error('Rate outside 0..120 Hz');
    pairs.push([i,c.rate_hz]);
  }
  rates.fill(0);for(const [i,rate] of pairs)rates[i]=rate;
  return new Set(pairs.map(p=>p[0]));
}
function run(steps,injected,silenced=false){
  const start=performance.now(),before=brain.tick;
  const result=brain.batch(steps,rates,silenced);
  let downstream=0,active=0;const top=[];const driven=[];
  for(let i=0;i<graph.n;i++)if(result.counts[i]){
    active++;const r={bodyId:String(neurons[i][0]),type:neurons[i][1],side:neurons[i][3],spikes:result.counts[i]};
    if(injected.has(i))driven.push(r);else{downstream+=r.spikes;top.push(r);}
  }
  top.sort((a,b)=>b.spikes-a.spikes);driven.sort((a,b)=>b.spikes-a.spikes);
  return {tick_before:before,tick_after:brain.tick,model_ms:steps*PARAMETERS.dt,
    model_elapsed_ms:brain.tick*PARAMETERS.dt,wall_ms:performance.now()-start,
    total_spikes:result.total,active_neurons:active,downstream_spikes:downstream,
    input_neuron_spikes:result.total-downstream,top_downstream:top.slice(0,12),top_input:driven.slice(0,12)};
}
const lines=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
for await(const line of lines){
  let id=null;
  try{
    const cmd=JSON.parse(line);id=cmd.id;
    if(cmd.command==='quit'){send({id,ok:true});break;}
    if(cmd.command==='reset'){brain.reset();rates.fill(0);send({id,ok:true,tick:brain.tick});continue;}
    if(!['step','controls'].includes(cmd.command))throw Error('Unknown command');
    const steps=cmd.steps;
    if(!Number.isInteger(steps)||steps<1||steps>10000)throw Error('steps must be 1..10000');
    const injected=input(cmd.channels);
    if(cmd.command==='step')send({id,ok:true,...run(steps,injected,Boolean(cmd.connections_off))});
    else{
      const saved=rates.slice(),runs={};
      for(const mode of ['no_input','camera','connections_off','half_gain']){
        brain.reset();rates.set(saved);
        if(mode==='no_input')rates.fill(0);
        if(mode==='half_gain')for(let i=0;i<rates.length;i++)rates[i]*=.5;
        runs[mode]=run(steps,injected,mode==='connections_off');
      }
      brain.reset();rates.fill(0);
      send({id,ok:true,runs,model_reset_after_controls:true});
    }
  }catch(e){send({id,ok:false,error:String(e.message||e)});}
}
