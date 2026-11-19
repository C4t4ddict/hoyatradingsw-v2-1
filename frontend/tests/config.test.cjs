const test = require('node:test')
const assert = require('node:assert/strict')
const config = require('../next.config.js')

test('dev and production do not write to the same output directory', () => {
  const dev = config('phase-development-server')
  const prod = config('phase-production-build')
  assert.notEqual(dev.distDir, prod.distDir)
  assert.equal(config('phase-production-server').distDir, prod.distDir)
})
