(function(global){
"use strict";

function defaultBuildTeamEntry(entry, coach, resolveMon, notes){
  var resolved=resolveMon(coach, entry.name);
  if(resolved.status==="corrected")notes.push({t:"fix",m:coach+": "+resolved.from+" → "+resolved.out});
  if(resolved.status==="ambiguous")notes.push({t:"warn",m:coach+": "+resolved.from+" is ambiguous ("+resolved.options.join(" / ")+") — used "+resolved.out});
  if(resolved.status==="unmatched")notes.push({t:"warn",m:coach+": "+resolved.from+" isn't on their roster — kept as-is"});
  return entry.k+entry.d+resolved.out;
}

function parseReplayUrl(wiglettText){
  var match=String(wiglettText||"").match(/https?:\/\/[^\s]+/);
  return match?match[0].replace(/[).,]+$/,""):"";
}

function parseScore(wiglettText){
  var match=String(wiglettText||"").match(/won\s+(\d+)\s*-\s*\d+/i);
  return match?match[1]:"?";
}

function extractWiglettTeamSegments(wiglettText, parseTeam){
  var body=String(wiglettText||"");
  var resultIndex=body.search(/Result:/i);
  if(resultIndex>=0)body=body.slice(resultIndex+7);
  var replayIndex=body.search(/Replay:/i);
  if(replayIndex>=0)body=body.slice(0,replayIndex);
  body=body.replace(/^[\s\S]*?won\s+\d+\s*-\s*\d+/i,"");
  var anchorRegex=/(?:^|\s)([^\s:]+):\s+[A-Za-z0-9'.\u2019-]/g;
  var anchors=[];
  var anchorMatch;
  while((anchorMatch=anchorRegex.exec(body))!==null){
    var colonPosition=body.indexOf(":",anchorMatch.index);
    anchors.push({labelEnd:colonPosition+1,matchStart:anchorMatch.index});
  }
  var segments=[];
  for(var i=0;i<anchors.length;i++){
    var start=anchors[i].labelEnd;
    var end=(i+1<anchors.length)?anchors[i+1].matchStart:body.length;
    var segment=body.slice(start,end);
    if(/has\s+\d+\s+kills?/i.test(segment))segments.push(parseTeam(segment));
  }
  return segments;
}

function buildBasicBattlePayload(options){
  var wiglettText=options.wiglettText||"";
  var winner=options.winner||"";
  var loser=options.loser||"";
  var parseTeam=options.parseTeam;
  var scoreSeg=options.scoreSeg;
  var resolveMon=options.resolveMon;

  if(!winner||!loser)throw new Error("Winner and loser are required.");
  if(winner===loser)throw new Error("Winner and loser must differ.");
  if(!wiglettText.trim())throw new Error("Paste the Wiglett output first.");
  if(!parseTeam||!scoreSeg||!resolveMon)throw new Error("Roster helpers are required.");

  var score=parseScore(wiglettText);
  var replayUrl=parseReplayUrl(wiglettText);
  var segments=extractWiglettTeamSegments(wiglettText, parseTeam);
  if(segments.length<2)throw new Error("Could not find two teams — check the pasted text.");

  var teamA=segments[0];
  var teamB=segments[1];
  var namesA=teamA.map(function(entry){return entry.name;});
  var namesB=teamB.map(function(entry){return entry.name;});
  var optionForward=scoreSeg(namesA,winner)+scoreSeg(namesB,loser);
  var optionReverse=scoreSeg(namesA,loser)+scoreSeg(namesB,winner);
  var winnerTeam=optionForward>=optionReverse?teamA:teamB;
  var loserTeam=optionForward>=optionReverse?teamB:teamA;
  var notes=[];
  var winnerPokemon=winnerTeam.slice().reverse().map(function(entry){
    return defaultBuildTeamEntry(entry, winner, resolveMon, notes);
  });
  var loserPokemon=loserTeam.slice().reverse().map(function(entry){
    return defaultBuildTeamEntry(entry, loser, resolveMon, notes);
  });
  var battleRow=["match",winner,loser,score,replayUrl].concat(winnerPokemon).concat(loserPokemon);

  return {
    battleRow:battleRow,
    battleRowCsv:battleRow.join(","),
    replayUrl:replayUrl,
    score:score,
    winner:winner,
    loser:loser,
    winnerPokemon:winnerPokemon,
    loserPokemon:loserPokemon,
    notes:notes
  };
}

function parseAdvancedStatsForReplay(options){
  var browserApi=options.browserApi;
  var input=options.input||{};
  if(!browserApi||!browserApi.parse_replay)throw new Error("Advanced stats parser is not ready.");
  var resultJson=browserApi.parse_replay(
    input.content||"",
    input.identifier||"unknown-battle",
    input.replayUrl||"",
    JSON.stringify(input.metadata||{})
  );
  var result=JSON.parse(resultJson);
  return {
    battleId:result.battle_id||input.identifier||"unknown-battle",
    replayUrl:input.replayUrl||"",
    pokemonRows:result.pokemon_rows||[],
    warnings:result.warnings||[],
    error:result.error||null
  };
}

function buildBattleSubmissionPayload(preview, replaceExisting){
  if(!preview||!preview.basicBattleRow||!preview.advancedStats)throw new Error("Preview the battle before submitting.");
  return {
    basicBattleRow:preview.basicBattleRow,
    replayUrl:preview.replayUrl,
    advancedStats:preview.advancedStats,
    warnings:preview.warnings||[],
    replaceExisting:Boolean(replaceExisting)
  };
}

function parseAppsScriptResponseText(text){
  var raw=String(text||"").trim();
  if(!raw)throw new Error("Apps Script returned an empty response.");
  var match=raw.match(/\{[\s\S]*\}/);
  if(match)raw=match[0];
  return JSON.parse(raw);
}

async function buildSingleBattleAutomationPayload(options){
  var basic=buildBasicBattlePayload(options);
  if(!basic.replayUrl)throw new Error("Could not find a replay URL in the Wiglett output.");
  if(!options.fetchReplayFromUrl)throw new Error("Replay fetcher is required.");
  var replayInput=await options.fetchReplayFromUrl(basic.replayUrl);
  var advanced=parseAdvancedStatsForReplay({browserApi:options.browserApi,input:replayInput});
  if(advanced.error)throw new Error(advanced.error);
  return {
    basicBattleRow:basic.battleRow,
    basicBattleRowCsv:basic.battleRowCsv,
    replayUrl:basic.replayUrl,
    advancedStats:advanced,
    warnings:basic.notes.filter(function(note){return note.t==="warn";}).map(function(note){return note.m;}).concat(advanced.warnings),
    notes:basic.notes
  };
}

global.ReplayAutomation={
  buildBasicBattlePayload:buildBasicBattlePayload,
  buildBattleSubmissionPayload:buildBattleSubmissionPayload,
  buildSingleBattleAutomationPayload:buildSingleBattleAutomationPayload,
  parseAdvancedStatsForReplay:parseAdvancedStatsForReplay,
  parseAppsScriptResponseText:parseAppsScriptResponseText,
  parseReplayUrl:parseReplayUrl
};
})(window);
