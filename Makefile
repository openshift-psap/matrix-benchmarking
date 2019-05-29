all:: benchmark.html
	./benchmark

benchmark.html: benchmark.md Makefile
	asciidoc -n -a icons -a toc -o $@ $<
