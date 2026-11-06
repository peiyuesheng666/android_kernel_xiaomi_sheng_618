// Read-only inspection of scheduling metadata; never edit application databases.
const { DatabaseSync } = require('node:sqlite');
const path = require('node:path');
const taskBase = path.join(process.env.USERPROFILE, '.codex');
for (const relative of ['sqlite/codex-dev.db', 'state_5.sqlite', 'queue_1.sqlite']) {
  const file = path.join(taskBase, relative);
  try {
    const db = new DatabaseSync(file, { readOnly: true });
    const tables = db.prepare("SELECT name, sql FROM sqlite_master WHERE type='table'").all();
    console.log(JSON.stringify({file, tables: tables.filter(row => /automat|heart|sched|job/i.test(row.name))}));
    if (tables.some(row => row.name === 'automations')) {
      const automation = db.prepare('SELECT id,status,next_run_at,last_run_at,next_run_nominal_at,rrule,kind,target_thread_id,model,created_at,updated_at FROM automations WHERE id=?').get('sheng-lineageos');
      const runs = db.prepare('SELECT thread_id,status,created_at,updated_at,archived_reason FROM automation_runs WHERE automation_id=? ORDER BY created_at DESC LIMIT 12').all('sheng-lineageos');
      console.log(JSON.stringify({automation: automation ?? null, runs}));
    }
    db.close();
  } catch (error) {
    console.log(JSON.stringify({file, error: error.message}));
  }
}
