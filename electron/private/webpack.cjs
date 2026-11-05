// SPDX-License-Identifier: MIT
const path = require('node:path');
const webpack = require('webpack');
const configuration = require('./build/webpack/webpack.config.isolated_renderer.js')({
  buildflags: process.argv[2], mode: 'development',
}, {'output-filename': path.basename(process.argv[3])});
// Declaration generation/typechecking is a separate unfinished producer.
for (const rule of configuration.module.rules) {
  if (rule.loader === 'ts-loader') rule.options.transpileOnly = true;
}
configuration.context = process.cwd();
configuration.output.path = path.dirname(process.argv[3]);
configuration.resolve.symlinks = true;
webpack(configuration, (error, stats) => {
  if (error || stats.hasErrors()) {
    console.error(error || stats.toString({all: false, errors: true}));
    process.exitCode = 1;
  }
});
