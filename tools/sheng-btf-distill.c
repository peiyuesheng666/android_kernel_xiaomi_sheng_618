// SPDX-License-Identifier: GPL-2.0-only
/* Host-only conversion, using the matching ACK libbpf implementation. */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "btf.h"
#include "libbpf.h"

static void fail(const char *what, int error)
{
	fprintf(stderr, "%s: %d\n", what, error);
	exit(EXIT_FAILURE);
}

static struct btf *checked(struct btf *btf, const char *what)
{
	long error = libbpf_get_error(btf);
	if (!btf || error)
		fail(what, error ? (int)error : -errno);
	return btf;
}

static void save(const char *path, const struct btf *btf)
{
	__u32 size;
	const void *data = btf__raw_data(btf, &size);
	FILE *file;
	if (!data)
		fail("btf__raw_data", -errno);
	file = fopen(path, "wb");
	if (!file)
		fail(path, -errno);
	if (fwrite(data, 1, size, file) != size)
		fail("write BTF", -EIO);
	if (fclose(file))
		fail("close BTF", -errno);
}

int main(int argc, char **argv)
{
	struct btf *base, *module, *dist_base = NULL, *dist_split = NULL;
	int error;
	if (argc != 6 || strcmp(argv[1], "distill")) {
		if (argc != 4 || strcmp(argv[1], "verify")) {
			fprintf(stderr, "Usage: %s distill CORE_BTF MODULE SPLIT_OUT BASE_OUT\n"
				"       %s verify FINAL_BTF MODULE\n", argv[0], argv[0]);
			return EXIT_FAILURE;
		}
	}
	base = checked(btf__parse_raw(argv[2]), "parse kernel BTF");
	/* With .BTF.base this parser invokes btf__relocate against base. */
	module = checked(btf__parse_elf_split(argv[3], base), "parse/relocate module BTF");
	if (!strcmp(argv[1], "distill")) {
		error = btf__distill_base(module, &dist_base, &dist_split);
		if (error)
			fail("btf__distill_base", error);
		save(argv[4], dist_split);
		save(argv[5], dist_base);
	}
	printf("{\"base_types\":%u,\"module_types\":%u,\"distilled_base_types\":%u}\n",
	       btf__type_cnt(base), btf__type_cnt(module) - btf__type_cnt(base),
	       dist_base ? btf__type_cnt(dist_base) : 0);
	btf__free(dist_split);
	btf__free(dist_base);
	btf__free(module);
	btf__free(base);
	return EXIT_SUCCESS;
}
