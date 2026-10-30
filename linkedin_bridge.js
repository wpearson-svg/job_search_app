// Calls the npm package linkedin-jobs-api (github.com/VishwaGauravIn/linkedin-jobs-api) for the Python app.
// Usage: node linkedin_bridge.js '{"keyword":"it support","location":"Kansas City","limit":"25"}'
// The package prints its own log lines with console.log, so those are sent to stderr and the result is printed on
// stdout between two markers that the Python side looks for.
const realWrite = process.stdout.write.bind(process.stdout);
console.log = console.info = console.warn = (...args) => console.error(...args);

const linkedIn = require("linkedin-jobs-api");
const options = JSON.parse(process.argv[2] || "{}");
linkedIn
  .query(options)
  .then((jobs) => realWrite("@@JSON@@" + JSON.stringify(jobs || []) + "@@END@@"))
  .catch((err) => {
    process.stderr.write(String((err && err.message) || err));
    process.exit(1);
  });
