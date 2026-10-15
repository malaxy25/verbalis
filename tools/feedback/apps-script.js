// Verbalis «Problem melden» – receives reports from the app (see src/verbalis/feedback.py).
//
// Setup (once):
// 1. New Google Sheet → Extensions → Apps Script → paste this file.
// 2. Project settings → Script properties:
//      TOKEN  = a long random value, the same as the GitHub secret VERBALIS_FEEDBACK_TOKEN
//      NOTIFY = e-mail address for a short notice per report (optional)
// 3. Deploy → New deployment → Web app: «Execute as: Me», «Who has access: Anyone».
//    The /exec URL goes into the GitHub secret VERBALIS_FEEDBACK_URL.
// After changing this script: Deploy → Manage deployments → edit → new version (the URL stays).

const FOLDER = "Verbalis-Meldungen";   // Google Drive folder for the log ZIPs

function doPost(e) {
  let report;
  try {
    report = JSON.parse(e.postData.contents);
  } catch (err) {
    return answer("bad request");
  }
  const props = PropertiesService.getScriptProperties();
  if (!report || !props.getProperty("TOKEN") || report.token !== props.getProperty("TOKEN")) {
    return answer("forbidden");
  }
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    let log = report.log_note || "";
    if (report.log_zip) {
      const name = "verbalis-log-" + Utilities.formatDate(new Date(), "Europe/Zurich", "yyyy-MM-dd_HHmmss") + ".zip";
      const blob = Utilities.newBlob(Utilities.base64Decode(report.log_zip), "application/zip", name);
      log = folder().createFile(blob).getUrl();
    }
    const sheet = sheetWithHeader("Meldungen", ["Zeit", "Version", "System", "Meldung", "Kontakt", "Log", "Diagnose"]);
    sheet.appendRow([new Date(), safe(report.version), safe(report.system), safe(report.message),
                     safe(report.contact), log, safe((report.diagnosis || "").slice(0, 45000))]);
    const notify = props.getProperty("NOTIFY");
    if (notify) {
      MailApp.sendEmail(notify, "Verbalis " + (report.version || "") + ": neue Meldung",
        (report.message || "") + "\n\nKontakt: " + (report.contact || "–") + "\nSystem: " + (report.system || "") +
        "\nLog: " + (log || "–") + "\n\n" + SpreadsheetApp.getActiveSpreadsheet().getUrl());
    }
  } finally {
    lock.releaseLock();
  }
  return answer("ok");
}

// A text starting with = + - @ would be run as a formula in the sheet.
function safe(value) {
  const text = String(value || "");
  return /^[=+\-@]/.test(text) ? "'" + text : text;
}

function sheetWithHeader(name, header) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    sheet.appendRow(header);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function folder() {
  const found = DriveApp.getFoldersByName(FOLDER);
  return found.hasNext() ? found.next() : DriveApp.createFolder(FOLDER);
}

function answer(text) {
  return ContentService.createTextOutput(text);
}
