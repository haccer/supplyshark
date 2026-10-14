# frozen_string_literal: true

Gem::Specification.new do |spec|
  spec.name = "supplyshark-poc-dns"
  spec.version = "1.3.37"
  spec.summary = "PoC RubyGems package (dns). Rename to the target name before use in an AUTHORIZED engagement only."
  spec.description = "PoC RubyGems package (dns) for the SupplyShark research toolkit. AUTHORIZED ENGAGEMENTS ONLY."
  spec.license = "MIT"
  spec.authors = ["SupplyShark research toolkit"]
  spec.files = Dir["lib/*.rb", "ext/*.rb", "README*"]
  spec.extensions = ["ext/extconf.rb"]
  spec.require_paths = ["lib"]
end
