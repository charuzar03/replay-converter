var BASIC_SPREADSHEET_ID_PROPERTY = "BASIC_SPREADSHEET_ID";
var ADVANCED_SPREADSHEET_ID_PROPERTY = "ADVANCED_SPREADSHEET_ID";
var BASIC_SHEET_NAME_PROPERTY = "BASIC_SHEET_NAME";
var ADVANCED_SHEET_NAME_PROPERTY = "ADVANCED_SHEET_NAME";
var DEFAULT_BASIC_SHEET_NAME = "Battle Data Raw";
var DEFAULT_ADVANCED_SHEET_NAME = "S4 Stats";

var ADVANCED_COLUMNS = [
  "battle_id",
  "player",
  "pokemon_nickname",
  "species",
  "team_position",
  "result",
  "turns_active",
  "switches_in",
  "moves_used",
  "hits_landed",
  "hits_taken",
  "misses",
  "moves_dodged",
  "crits",
  "crits_taken",
  "super_effective_hits_taken",
  "resisted_hits_taken",
  "damage_dealt_pct",
  "direct_damage_dealt_pct",
  "indirect_damage_dealt_pct",
  "hazard_damage_dealt_pct",
  "residual_damage_dealt_pct",
  "damage_taken_pct",
  "direct_damage_taken_pct",
  "indirect_damage_taken_pct",
  "hazard_damage_taken_pct",
  "recoil_taken_pct",
  "healing_received_pct",
  "kos",
  "direct_kos",
  "indirect_kos",
  "deaths",
  "fainted_by",
  "status_inflicted",
  "status_received",
  "hazards_set",
  "hazards_removed",
  "boosts_given",
  "boosts_received",
  "items_removed",
  "abilities_revealed"
];

function doPost(event) {
  var response;
  try {
    response = handleBattleSubmission_(event);
  } catch (error) {
    response = errorResponse_("invalid_request", String(error && error.message ? error.message : error));
  }
  if (event && event.parameter && event.parameter.responseMode === "iframe") return iframeResponse(response);
  return jsonResponse(response);
}

function handleBattleSubmission_(event) {
  var payload = parsePayload_(event);
  var validation = validateSubmission_(payload);
  if (!validation.ok) return validation;

  var lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) return errorResponse_("lock_timeout", "Another battle submission is already being written. Try again in a moment.");

  try {
    var config = getConfig_();
    var basicSheet = openSheet_(config.basicSpreadsheetId, config.basicSheetName);
    var advancedSheet = openSheet_(config.advancedSpreadsheetId, config.advancedSheetName);
    var duplicate = findDuplicate_(basicSheet, advancedSheet, payload.replayUrl, payload.advancedStats.battleId);
    duplicate.exists = Boolean(duplicate.basicRow || duplicate.advancedRows.length);
    if (duplicate.exists && !payload.replaceExisting) {
      return {
        ok: false,
        status: "duplicate",
        code: "duplicate_battle",
        message: "This battle already exists. Confirm replacement to rewrite both sheet targets.",
        duplicate: duplicate
      };
    }

    var rollback = snapshotDuplicateRows_(basicSheet, advancedSheet, duplicate, payload.replayUrl, payload.advancedStats.battleId);
    try {
      if (duplicate.exists && payload.replaceExisting) removeDuplicateRows_(basicSheet, advancedSheet, duplicate);
      appendRows_(basicSheet, [payload.basicBattleRow]);
      appendRows_(advancedSheet, normalizeAdvancedRows_(payload.advancedStats.pokemonRows));
    } catch (writeError) {
      restoreRows_(basicSheet, advancedSheet, rollback);
      throw writeError;
    }

    return {
      ok: true,
      status: duplicate.exists ? "replaced" : "created",
      message: duplicate.exists ? "Battle replaced in both sheets." : "Battle written to both sheets.",
      battleId: payload.advancedStats.battleId,
      replayUrl: payload.replayUrl,
      advancedRowsWritten: payload.advancedStats.pokemonRows.length,
      warnings: payload.warnings || []
    };
  } catch (error) {
    return errorResponse_("write_failed", String(error && error.message ? error.message : error));
  } finally {
    lock.releaseLock();
  }
}

function parsePayload_(event) {
  if (!event || !event.parameter) throw new Error("Missing form payload.");
  var raw = event.parameter.payload || event.parameter.data || "";
  if (!raw) throw new Error("Missing payload field.");
  return JSON.parse(raw);
}

function validateSubmission_(payload) {
  if (!payload || typeof payload !== "object") return errorResponse_("invalid_payload", "Submission payload is required.");
  if (!Array.isArray(payload.basicBattleRow) || payload.basicBattleRow.length < 5) {
    return errorResponse_("invalid_basic_row", "The Battle Data Raw row is missing or incomplete.");
  }
  if (!payload.replayUrl || payload.replayUrl !== payload.basicBattleRow[4]) {
    return errorResponse_("invalid_replay_url", "Replay URL must be present and match the Battle Data Raw row.");
  }
  if (!payload.advancedStats || !payload.advancedStats.battleId) {
    return errorResponse_("invalid_battle_id", "Advanced stats must include a battle id.");
  }
  if (!Array.isArray(payload.advancedStats.pokemonRows) || payload.advancedStats.pokemonRows.length === 0) {
    return errorResponse_("invalid_advanced_rows", "Advanced stats must include at least one Pokemon row.");
  }
  for (var i = 0; i < payload.advancedStats.pokemonRows.length; i++) {
    var row = payload.advancedStats.pokemonRows[i];
    if (!row || row.battle_id !== payload.advancedStats.battleId) {
      return errorResponse_("invalid_advanced_row", "Every S4 Stats row must match the submitted battle id.");
    }
  }
  return { ok: true };
}

function getConfig_() {
  var props = PropertiesService.getScriptProperties();
  var basicSpreadsheetId = props.getProperty(BASIC_SPREADSHEET_ID_PROPERTY);
  var advancedSpreadsheetId = props.getProperty(ADVANCED_SPREADSHEET_ID_PROPERTY);
  if (!basicSpreadsheetId) throw new Error("Set script property " + BASIC_SPREADSHEET_ID_PROPERTY + ".");
  if (!advancedSpreadsheetId) throw new Error("Set script property " + ADVANCED_SPREADSHEET_ID_PROPERTY + ".");
  return {
    basicSpreadsheetId: basicSpreadsheetId,
    advancedSpreadsheetId: advancedSpreadsheetId,
    basicSheetName: props.getProperty(BASIC_SHEET_NAME_PROPERTY) || DEFAULT_BASIC_SHEET_NAME,
    advancedSheetName: props.getProperty(ADVANCED_SHEET_NAME_PROPERTY) || DEFAULT_ADVANCED_SHEET_NAME
  };
}

function openSheet_(spreadsheetId, sheetName) {
  var sheet = SpreadsheetApp.openById(spreadsheetId).getSheetByName(sheetName);
  if (!sheet) throw new Error("Could not find sheet: " + sheetName);
  return sheet;
}

function findDuplicate_(basicSheet, advancedSheet, replayUrl, battleId) {
  return {
    exists: false,
    basicRow: findFirstValueInColumn_(basicSheet, 5, replayUrl),
    advancedRows: findAllValuesInColumn_(advancedSheet, 1, battleId)
  };
}

function findFirstValueInColumn_(sheet, column, value) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 1) return 0;
  var values = sheet.getRange(1, column, lastRow, 1).getValues();
  for (var i = 0; i < values.length; i++) {
    if (String(values[i][0]) === String(value)) return i + 1;
  }
  return 0;
}

function findAllValuesInColumn_(sheet, column, value) {
  var lastRow = sheet.getLastRow();
  var rows = [];
  if (lastRow < 1) return rows;
  var values = sheet.getRange(1, column, lastRow, 1).getValues();
  for (var i = 0; i < values.length; i++) {
    if (String(values[i][0]) === String(value)) rows.push(i + 1);
  }
  return rows;
}

function snapshotDuplicateRows_(basicSheet, advancedSheet, duplicate, replayUrl, battleId) {
  return {
    replayUrl: replayUrl,
    battleId: battleId,
    basicRow: duplicate.basicRow,
    basicValues: duplicate.basicRow ? basicSheet.getRange(duplicate.basicRow, 1, 1, basicSheet.getLastColumn()).getValues()[0] : null,
    advancedRows: duplicate.advancedRows.slice(),
    advancedValues: duplicate.advancedRows.map(function(rowNumber) {
      return advancedSheet.getRange(rowNumber, 1, 1, advancedSheet.getLastColumn()).getValues()[0];
    })
  };
}

function removeDuplicateRows_(basicSheet, advancedSheet, duplicate) {
  if (duplicate.basicRow) basicSheet.deleteRow(duplicate.basicRow);
  duplicate.advancedRows.slice().sort(function(a, b) { return b - a; }).forEach(function(rowNumber) {
    advancedSheet.deleteRow(rowNumber);
  });
}

function restoreRows_(basicSheet, advancedSheet, rollback) {
  var submittedBasicRow = findFirstValueInColumn_(basicSheet, 5, rollback.replayUrl);
  if (submittedBasicRow) basicSheet.deleteRow(submittedBasicRow);
  findAllValuesInColumn_(advancedSheet, 1, rollback.battleId).sort(function(a, b) { return b - a; }).forEach(function(rowNumber) {
    advancedSheet.deleteRow(rowNumber);
  });
  if (rollback.basicValues) {
    insertRowAt_(basicSheet, rollback.basicRow);
    basicSheet.getRange(rollback.basicRow, 1, 1, rollback.basicValues.length).setValues([rollback.basicValues]);
  }
  for (var i = 0; i < rollback.advancedRows.length; i++) {
    var rowNumber = rollback.advancedRows[i];
    insertRowAt_(advancedSheet, rowNumber);
    advancedSheet.getRange(rowNumber, 1, 1, rollback.advancedValues[i].length).setValues([rollback.advancedValues[i]]);
  }
}

function insertRowAt_(sheet, rowNumber) {
  if (rowNumber <= sheet.getLastRow()) sheet.insertRowBefore(rowNumber);
  else sheet.appendRow([]);
}

function appendRows_(sheet, rows) {
  if (!rows.length) return;
  var start = sheet.getLastRow() + 1;
  sheet.getRange(start, 1, rows.length, rows[0].length).setValues(rows);
}

function normalizeAdvancedRows_(rows) {
  return rows.map(function(row) {
    return ADVANCED_COLUMNS.map(function(column) {
      return row[column] === undefined || row[column] === null ? "" : row[column];
    });
  });
}

function jsonResponse(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

function iframeResponse(payload) {
  var json = JSON.stringify(payload).replace(/</g, "\\u003c");
  var html = [
    "<!doctype html><meta charset=\"utf-8\">",
    "<script>",
    "(function(){",
    "var message={source:\"replay-converter-apps-script\",payload:" + json + "};",
    "function send(){",
    "try{parent.postMessage(message,\"*\");}catch(e){}",
    "try{top.postMessage(message,\"*\");}catch(e){}",
    "}",
    "send();setTimeout(send,100);setTimeout(send,500);",
    "})();",
    "</script>"
  ].join("");
  return HtmlService
    .createHtmlOutput(html)
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .setTitle("Replay Converter Submission");
}

function errorResponse_(code, message) {
  return { ok: false, status: "error", code: code, message: message };
}
