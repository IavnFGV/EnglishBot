# Catalog Workbook

This workflow exists for centralized bulk editing when Telegram UI is too narrow for large vocabulary catalogs.

The application database remains the source of truth. The workbook is an import/export surface on top of that DB.

## What It Solves

Use the workbook flow when you need to:

- review many words grouped by topic outside Telegram
- add or update words in topics without thinking about internal DB ids
- update image links, prompts, and search queries in bulk

The workbook is text-only. It does not embed binary images and it does not import local image files.

## Telegram Entry Point

Admins can open this flow from the bot:

1. `/words`
2. `Catalog Workbook`
3. `Export Workbook` or `Import Workbook`

`Import Workbook` expects an edited `.xlsx` file back in Telegram.

## CLI

Export a workbook from the current DB:

```bash
python -m englishbot.media_catalog export-workbook --output exports/catalog.xlsx
```

Export only one topic:

```bash
python -m englishbot.media_catalog export-workbook \
  --output exports/animals-catalog.xlsx \
  --topic-id animals
```

Import workbook edits back into the DB:

```bash
python -m englishbot.media_catalog import-workbook --input exports/catalog.xlsx
```

## Workbook Sheets

The export contains only two sheets:

- `topics`
- `words_in_topics`

## Topics Sheet

`topics` contains one editable column:

- `topic_title`

Rules:

- topic titles must be unique
- admins can add new topics here
- internal `topic_id` values are not exposed in the workbook

## Words Sheet

The main editable sheet is `words_in_topics`.

Columns:

- `topic_title`
- `english_word`
- `translation`
- `meaning_hint`
- `preview`
- `image_ref`
- `image_source`
- `image_prompt`
- `pixabay_search_query`
- `source_fragment`
- `is_active`

One row means one word in one topic.

## Image Fields

For image editing in the workbook:

- `preview` is an export-only helper column that shows the current image
- put the desired image link into `image_ref`
- if `image_ref` contains an `http` or `https` URL, the importer downloads that image into local `assets/<topic>/<item>.<ext>`
- after download, the DB stores the local asset path in `image_ref`
- the original remote URL is preserved in `image_source` when `image_source` was empty

This keeps the runtime on local assets even if the editor works with remote URLs in the workbook.

For local runtime images, the `preview` cell uses a signed URL from the server so Google Sheets can render the image without exposing the raw assets directory.

## Editing Model

Admins should think in this model:

- topic
- word in that topic
- translation
- image-related fields

Example:

- `Fairy Tales | fairy | фея | ...`
- `Cleaning Stuff | fairy | Fairy | ...`

## Import Rules

- Import reads the `topics` and `words_in_topics` sheets.
- Every `words_in_topics.topic_title` must exist in the `topics` sheet.
- If `topic_title` already exists in the DB, the importer uses that topic.
- If `topic_title` does not exist in the DB, the importer creates a new topic and generates an internal `topic_id`.
- Inside one topic, existing rows are matched by `english_word`.
- If the word already exists in that topic, the importer updates it.
- If the word does not exist in that topic, the importer creates a new row for that topic.
- Internal `item_id`, `topic_id`, and `lexeme_id` values are handled only by the importer and DB.

## Important Notes

- The workbook is an editing surface, not a production source of truth.
- Imports rewrite vocabulary rows for the topics present in `words_in_topics`.
- Existing lessons for those topics are preserved during import.
- Before applying workbook changes, the importer creates a SQLite backup snapshot in `data/backups/`.
- Topics not present in the workbook stay untouched.
- If you need to handle hundreds of words, exporting one topic at a time is usually easier to review.
- `image_ref` is the only workbook column used to replace the image source.
- `preview` is ignored by import and exists only for easier browsing in spreadsheets.

## Rollback

If a workbook import needs to be reversed:

1. Stop the bot process.
2. Locate the latest pre-import backup in `data/backups/`.
3. Replace the active DB file with that backup.
4. Start the bot again.

The importer creates the backup before applying workbook changes, and topic updates are applied atomically inside one SQLite transaction. This means:

- if import fails before commit, SQLite rolls back the workbook changes automatically
- if import succeeds but the result is wrong, you can restore the last pre-import backup manually

Example rollback flow:

```bash
cp data/backups/englishbot-pre-import-YYYYMMDD-HHMMSS.db data/englishbot.db
```

Use the backup path printed by the CLI import command when available.
