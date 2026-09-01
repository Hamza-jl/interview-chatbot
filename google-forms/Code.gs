/**
 * Deux Google Forms pour l'ensemble des entités.
 *
 *   • « Entités »  : le plan court, précédé d'une liste déroulante où le
 *                    correspondant choisit sa structure.
 *   • « DSI »      : le plan long, réservé aux Systèmes d'Information.
 *
 * Les réponses arrivent dans un classeur unique. Un déclencheur les recopie au
 * fil de l'eau dans un onglet par structure, créé à la première réponse.
 *
 * Un formulaire par structure serait plus simple à router, mais coûtait
 * 32 créations à ~65 s pièce - au-delà de la limite de 6 minutes d'Apps Script,
 * donc six relances manuelles - et 32 liens à diffuser puis à régénérer à
 * chaque évolution du plan. Deux formulaires se créent en une seule exécution.
 *
 * Le plan vit dans Questions.gs, généré depuis le blueprint de l'application :
 * les deux canaux de collecte posent exactement les mêmes questions.
 *
 * UTILISATION
 *   1. script.google.com -> Nouveau projet
 *   2. Collez Code.gs et Questions.gs dans deux fichiers
 *   3. setUp()        (autorisez au premier lancement)
 *   4. createForms()  (une seule exécution suffit)
 *   5. listForms()    -> les deux liens à diffuser
 */

var ROOT_FOLDER_NAME = 'Etat des lieux - Formulaires';
var RESPONSES_NAME = 'Etat des lieux - Reponses';

// Le séparateur de colonnes des questions tableau : celui que l'application
// sait déjà analyser sans modèle.
var CELL_SEPARATOR = '|';

// L'intitulé exact de la liste déroulante. L'import s'appuie dessus pour
// savoir de quelle entité relève chaque ligne - ne le changez pas sans changer
// STRUCTURE_COLUMN dans app/scripts/from_forms.py.
var STRUCTURE_QUESTION = 'Structure documentée';

var PROPS = PropertiesService.getScriptProperties();


/* ------------------------------------------------------------------ setup */

/** Crée le dossier et le classeur de réponses. Une seule fois. */
function setUp() {
  var folder = getOrCreateFolder_();
  var sheet = getOrCreateResponseSheet_(folder);
  Logger.log('Dossier   : %s', folder.getUrl());
  Logger.log('Réponses  : %s', sheet.getUrl());
  Logger.log('Structures au plan : %s', String(SPEC.structures.length));
  return { folder: folder.getUrl(), responses: sheet.getUrl() };
}


function getOrCreateFolder_() {
  var id = PROPS.getProperty('folderId');
  if (id) {
    try { return DriveApp.getFolderById(id); } catch (e) { /* recréé ci-dessous */ }
  }
  var existing = DriveApp.getFoldersByName(ROOT_FOLDER_NAME);
  var folder = existing.hasNext() ? existing.next() : DriveApp.createFolder(ROOT_FOLDER_NAME);
  PROPS.setProperty('folderId', folder.getId());
  return folder;
}


function getOrCreateResponseSheet_(folder) {
  var id = PROPS.getProperty('sheetId');
  if (id) {
    try { return SpreadsheetApp.openById(id); } catch (e) { /* recréé ci-dessous */ }
  }
  var sheet = SpreadsheetApp.create(RESPONSES_NAME);
  var file = DriveApp.getFileById(sheet.getId());
  folder.addFile(file);
  DriveApp.getRootFolder().removeFile(file);
  PROPS.setProperty('sheetId', sheet.getId());
  return sheet;
}


function entityStructures_() {
  var out = [];
  for (var i = 0; i < SPEC.structures.length; i++) {
    if (SPEC.structures[i].templateKind !== 'dsi') { out.push(SPEC.structures[i]); }
  }
  return out;
}


function dsiStructure_() {
  for (var i = 0; i < SPEC.structures.length; i++) {
    if (SPEC.structures[i].templateKind === 'dsi') { return SPEC.structures[i]; }
  }
  throw new Error('Aucune structure au modèle DSI dans le plan.');
}


/** L'étiquette affichée dans la liste déroulante, et écrite dans le classeur. */
function structureChoice_(structure) {
  return structure.name + ' (' + structure.code + ')';
}


/* ------------------------------------------------------------- génération */

/** Crée les deux formulaires. Remplace les précédents s'ils existent. */
function createForms() {
  var folder = getOrCreateFolder_();
  var sheet = getOrCreateResponseSheet_(folder);

  var entities = buildEntityForm_(folder, sheet);
  var dsi = buildDsiForm_(folder, sheet);

  PROPS.setProperty('formIds', JSON.stringify({
    entite: entities.getId(),
    dsi: dsi.getId()
  }));

  installRouter_(sheet);

  Logger.log('Entités (%s structures) : %s',
             String(entityStructures_().length), entities.getPublishedUrl());
  Logger.log('DSI                     : %s', dsi.getPublishedUrl());
  Logger.log('Réponses                : %s', sheet.getUrl());
  return { entite: entities.getPublishedUrl(), dsi: dsi.getPublishedUrl() };
}


function buildEntityForm_(folder, sheet) {
  var plan = SPEC.plans.entite;
  var title = 'État des lieux — Entités';
  var form = FormApp.create(title);

  form.setTitle(title)
      .setDescription(
        "Recensement de la continuité d'activité de votre entité.\n\n" +
        plan.questions.length + " points, après le choix de votre structure. " +
        "Vous pouvez revenir corriger vos réponses : conservez le lien de " +
        "modification envoyé par courriel après envoi.\n\n" +
        'Répondez avec vos mots. Les questions « une ligne par … » attendent un ' +
        'tableau : une ligne par entrée, colonnes séparées par « ' + CELL_SEPARATOR + ' ».')
      .setCollectEmail(true)
      .setProgressBar(true)
      .setAllowResponseEdits(true)
      .setLimitOneResponsePerUser(false)
      .setConfirmationMessage(
        'Merci. Vos réponses sont enregistrées et seront reprises dans le ' +
        "document d'état des lieux de votre entité.");

  // Le choix de la structure d'abord : c'est lui qui décide de l'onglet dans
  // lequel la réponse atterrit, et de l'entité portée par le document.
  var structures = entityStructures_();
  var choices = [];
  for (var i = 0; i < structures.length; i++) {
    choices.push(structureChoice_(structures[i]));
  }
  form.addListItem()
      .setTitle(STRUCTURE_QUESTION)
      .setHelpText('Sélectionnez l\'entité que vous documentez. ' +
                   'Ce choix détermine le document qui sera produit.')
      .setChoiceValues(choices)
      .setRequired(true);

  addPlan_(form, plan);
  attach_(form, folder, sheet);
  return form;
}


function buildDsiForm_(folder, sheet) {
  var structure = dsiStructure_();
  var plan = SPEC.plans.dsi;
  var title = 'État des lieux — ' + structure.name;
  var form = FormApp.create(title);

  form.setTitle(title)
      .setDescription(
        "Recensement de la continuité d'activité de l'entité " + structure.name +
        ' (' + structure.code + ").\n\n" +
        plan.questions.length + ' points. Ce formulaire suit le plan étendu, ' +
        "propre au système d'information.\n\n" +
        'Les questions « une ligne par … » attendent un tableau : une ligne par ' +
        'entrée, colonnes séparées par « ' + CELL_SEPARATOR + ' ».')
      .setCollectEmail(true)
      .setProgressBar(true)
      .setAllowResponseEdits(true)
      .setLimitOneResponsePerUser(false)
      .setConfirmationMessage(
        'Merci. Vos réponses sont enregistrées et seront reprises dans le ' +
        "document d'état des lieux de " + structure.name + '.');

  // Une seule structure possible : la question existe quand même, en lecture
  // seule de fait, pour que les deux formulaires produisent la même colonne.
  form.addListItem()
      .setTitle(STRUCTURE_QUESTION)
      .setChoiceValues([structureChoice_(structure)])
      .setRequired(true);

  addPlan_(form, plan);
  attach_(form, folder, sheet);
  return form;
}


function addPlan_(form, plan) {
  var currentSection = null;
  for (var i = 0; i < plan.questions.length; i++) {
    var question = plan.questions[i];
    if (question.section !== currentSection) {
      currentSection = question.section;
      form.addSectionHeaderItem().setTitle(currentSection);
    }
    addQuestion_(form, question);
  }
}


function attach_(form, folder, sheet) {
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());
  var file = DriveApp.getFileById(form.getId());
  folder.addFile(file);
  DriveApp.getRootFolder().removeFile(file);
}


/* ------------------------------------------------------------- questions */

function addQuestion_(form, question) {
  if (question.kind === 'grid') { return addGridQuestion_(form, question); }

  var item = question.kind === 'field'
    ? form.addTextItem()
    : form.addParagraphTextItem();

  item.setTitle(question.label)
      .setHelpText(helpFor_(question))
      .setRequired(!question.optional);
  return item;
}


/**
 * Un tableau devient une question longue, une ligne par entrée.
 *
 * Google Forms n'a pas de tableau à saisie libre - ses « grilles » sont des
 * échelles de notation. Une question par cellule donnerait des formulaires de
 * plusieurs centaines de champs, avec un nombre de lignes figé d'avance. Le
 * texte séparé par « | » ne borne pas le nombre de lignes, et l'application
 * sait déjà l'analyser sans modèle.
 */
function addGridQuestion_(form, question) {
  var columns = [];
  for (var i = 0; i < question.columns.length; i++) {
    columns.push(question.columns[i].label);
  }

  var help = [];
  help.push('Une ligne par entrée. Colonnes, dans l\'ordre, séparées par « ' +
            CELL_SEPARATOR + ' » :');
  help.push('    ' + columns.join('  ' + CELL_SEPARATOR + '  '));

  var constrained = [];
  for (var j = 0; j < question.columns.length; j++) {
    var column = question.columns[j];
    if (column.choices && column.choices.length) {
      constrained.push('• ' + column.label + ' : ' + column.choices.join(' / '));
    } else if (column.hint) {
      constrained.push('• ' + column.label + ' : ' + column.hint);
    }
  }
  if (constrained.length) {
    help.push('');
    help.push('Valeurs attendues :');
    help.push(constrained.join('\n'));
  }

  if (question.example) {
    help.push('');
    help.push('Exemple :');
    help.push('    ' + question.example);
  }
  if (question.help) {
    help.push('');
    help.push(question.help);
  }

  return form.addParagraphTextItem()
             .setTitle(question.label)
             .setHelpText(help.join('\n'))
             .setRequired(!question.optional);
}


function helpFor_(question) {
  var parts = [];
  if (question.prompt) { parts.push(question.prompt); }
  if (question.help) { parts.push(question.help); }
  if (question.example) { parts.push('Exemple : ' + question.example); }
  return parts.join('\n\n');
}


/* ---------------------------------------------------- routage par entité */

/**
 * Un onglet par structure, alimenté à chaque envoi.
 *
 * Les onglets bruts que Google alimente restent la source de vérité : ceux-ci
 * en sont une vue, reconstructible à tout moment par rebuildStructureSheets().
 * Un déclencheur manqué ne perd donc rien.
 */
function installRouter_(sheet) {
  var existing = ScriptApp.getProjectTriggers();
  for (var i = 0; i < existing.length; i++) {
    if (existing[i].getHandlerFunction() === 'routeResponse') {
      ScriptApp.deleteTrigger(existing[i]);
    }
  }
  ScriptApp.newTrigger('routeResponse')
           .forSpreadsheet(sheet)
           .onFormSubmit()
           .create();
  Logger.log('Déclencheur de routage installé.');
}


/** Déclenché à chaque envoi de formulaire. Ne jamais appeler à la main. */
function routeResponse(e) {
  if (!e || !e.range) { return; }
  var source = e.range.getSheet();
  var header = source.getRange(1, 1, 1, source.getLastColumn()).getValues()[0];
  var row = source.getRange(e.range.getRow(), 1, 1, source.getLastColumn()).getValues()[0];
  copyToStructureSheet_(source.getParent(), header, row);
}


function copyToStructureSheet_(spreadsheet, header, row) {
  var index = -1;
  for (var i = 0; i < header.length; i++) {
    if (String(header[i]).trim() === STRUCTURE_QUESTION) { index = i; }
  }
  if (index < 0) { return null; }

  var label = String(row[index] || '').trim();
  if (!label) { return null; }

  var name = sheetNameFor_(label);
  var target = spreadsheet.getSheetByName(name);
  if (!target) {
    target = spreadsheet.insertSheet(name);
    target.appendRow(header);
    target.setFrozenRows(1);
  }
  target.appendRow(row);
  return target;
}


/**
 * « ACF - Audit Comptable et Fin » : le code d'abord, parce que l'export .xlsx
 * tronque un nom d'onglet à 31 caractères et couperait le nom de l'entité.
 */
function sheetNameFor_(label) {
  var code = label.match(/\(([^)]+)\)\s*$/);
  var name = label.replace(/\s*\([^)]*\)\s*$/, '').trim();
  var prefix = code ? code[1] + ' - ' : '';
  return (prefix + name).substring(0, 31);
}


/** Reconstruit tous les onglets par structure depuis les réponses brutes. */
function rebuildStructureSheets() {
  var spreadsheet = getOrCreateResponseSheet_(getOrCreateFolder_());
  var sheets = spreadsheet.getSheets();
  var known = {};
  for (var i = 0; i < SPEC.structures.length; i++) {
    known[sheetNameFor_(structureChoice_(SPEC.structures[i]))] = true;
  }

  // On repart des onglets alimentés par Google, jamais des vues dérivées.
  var sources = [];
  for (var j = 0; j < sheets.length; j++) {
    var name = sheets[j].getName();
    if (!known[name] && name !== 'Liens') { sources.push(sheets[j]); }
  }

  for (var k = 0; k < sheets.length; k++) {
    if (known[sheets[k].getName()]) { spreadsheet.deleteSheet(sheets[k]); }
  }

  var copied = 0;
  for (var s = 0; s < sources.length; s++) {
    var source = sources[s];
    if (source.getLastRow() < 2) { continue; }
    var values = source.getRange(1, 1, source.getLastRow(), source.getLastColumn()).getValues();
    var header = values[0];
    for (var r = 1; r < values.length; r++) {
      if (copyToStructureSheet_(spreadsheet, header, values[r])) { copied++; }
    }
  }
  Logger.log('%s réponse(s) reventilée(s).', String(copied));
  return copied;
}


/* ----------------------------------------------------------------- sortie */

/** Écrit un onglet « Liens » avec les deux formulaires. */
function listForms() {
  var ids = JSON.parse(PROPS.getProperty('formIds') || '{}');
  var spreadsheet = getOrCreateResponseSheet_(getOrCreateFolder_());

  var tab = spreadsheet.getSheetByName('Liens') || spreadsheet.insertSheet('Liens', 0);
  tab.clear();
  tab.appendRow(['Formulaire', 'Pour', 'Points', 'Lien à diffuser', 'Lien d\'édition']);

  var rows = [
    ['Entités', entityStructures_().length + ' structures, au choix dans le formulaire',
     SPEC.plans.entite.questions.length, ids.entite],
    ['DSI', dsiStructure_().name, SPEC.plans.dsi.questions.length, ids.dsi]
  ];

  for (var i = 0; i < rows.length; i++) {
    var id = rows[i][3];
    if (!id) {
      tab.appendRow([rows[i][0], rows[i][1], rows[i][2], 'PAS ENCORE CRÉÉ', '']);
      continue;
    }
    var form = FormApp.openById(id);
    tab.appendRow([rows[i][0], rows[i][1], rows[i][2],
                   form.getPublishedUrl(), form.getEditUrl()]);
  }
  tab.setFrozenRows(1);
  tab.autoResizeColumns(1, 5);

  Logger.log('Liens écrits dans : %s', spreadsheet.getUrl());
  return spreadsheet.getUrl();
}


/**
 * Met à la corbeille tout formulaire créé par ce projet - y compris les 32
 * d'une génération précédente. Le classeur de réponses est conservé.
 */
function deleteAllForms() {
  var removed = 0;

  var ids = JSON.parse(PROPS.getProperty('formIds') || '{}');
  for (var key in ids) {
    try { DriveApp.getFileById(ids[key]).setTrashed(true); removed++; } catch (e) {}
  }
  PROPS.deleteProperty('formIds');

  var legacy = JSON.parse(PROPS.getProperty('created') || '{}');
  for (var code in legacy) {
    try { DriveApp.getFileById(legacy[code]).setTrashed(true); removed++; } catch (e) {}
  }
  PROPS.deleteProperty('created');

  Logger.log('%s formulaire(s) mis à la corbeille.', String(removed));
  return removed;
}
