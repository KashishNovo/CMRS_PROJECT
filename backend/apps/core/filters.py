import django_filters


class DateRangeFilterSet(django_filters.FilterSet):
    """Adds ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD on the field named by `date_field` (inclusive)."""

    date_field = "created_at"
    date_from = django_filters.DateFilter(method="filter_date_from")
    date_to = django_filters.DateFilter(method="filter_date_to")

    def _lookup(self, suffix):
        field = self.date_field
        # DateTimeFields compare on their local date; DateFields directly.
        model_field = self._meta.model._meta.get_field(field)
        prefix = f"{field}__date" if model_field.get_internal_type() == "DateTimeField" else field
        return f"{prefix}__{suffix}"

    def filter_date_from(self, qs, name, value):
        return qs.filter(**{self._lookup("gte"): value})

    def filter_date_to(self, qs, name, value):
        return qs.filter(**{self._lookup("lte"): value})
