-- Gambit Ridge Capital : transport HTTP du complement Excel sur Mac (Excel ne sait pas lire le web en VBA).
-- Appele par AppleScriptTask("GambitRidge.scpt", "recuperer", url) ; installe par installer_mac.sh.
on recuperer(adresse)
	if adresse does not start with "http://" and adresse does not start with "https://" then return "#N/A Adresse invalide"
	try
		return do shell script "/usr/bin/curl -s -m 60 " & quoted form of adresse without altering line endings
	on error
		return "#N/A Terminal injoignable"
	end try
end recuperer
