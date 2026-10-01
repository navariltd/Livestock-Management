class CustomQualityInspection:
	def validate(self):
		# Temporarily set fields to avoid mandatory error
		if not self.inspection_type:
			self.inspection_type = None
		if not self.reference_type:
			self.reference_type = None
		if not self.reference_name:
			self.reference_name = None
		super().validate()

	def update_qc_reference(self, remove_reference=False):
		if not self.reference_type or not self.reference_name:
			return

		super().update_qc_reference(remove_reference=remove_reference)
