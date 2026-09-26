from typing import Optional, List
import os
from dotenv import load_dotenv

class Config:
	""" Configuration handler for environment variables and user prompts. """
	def __init__(self, values: Optional[dict] = None):
		"""
		Initialize Config.

		Args:
			values: Optional dict of pre-populated values (for UI/programmatic use).
					When provided, bypasses .env and prompts entirely.
		"""
		self.values = values or {}

		# Skip .env loading if values dict provided (UI mode)
		if self.values:
			self.use_env = True  # Prevents prompting, uses values dict
			return

		# Original CLI behavior
		if not os.path.exists('.env'):
			print(".env file not found. Continuing in interactive mode.")
			self.use_env = False
		else:
			load_dotenv(override=True)
			self.use_env = self.get_yes_no_input("Use .env settings? (y/n): ")

	def get_bool(self, val, prompt: Optional[str] = None):
		# Check values dict first (UI mode)
		if self.values and val in self.values:
			value = self.values[val]
			# Handle both boolean and string values
			if isinstance(value, bool):
				return value
			return str(value).lower() == 'true'

		# Original CLI behavior
		if self.use_env:
			env_val = os.getenv(val, 'false')
			return env_val.lower() == 'true'
		elif prompt is not None:
			return self.get_yes_no_input(prompt)
		return None

	def get_env(self, val, prompt: Optional[str] = None, valid_options: Optional[List[str]] = None, case_sensitive: bool = False):
		# Check values dict first (UI mode)
		if self.values and val in self.values:
			return self.values[val]

		# Original CLI behavior
		if self.use_env:
			return os.getenv(val)
		elif prompt is not None:
			return self.get_validated_input(prompt, valid_options=valid_options, case_sensitive=case_sensitive)
		return None

	def get_pkeys(self, valid_options: Optional[List[str]] = None, pkey_assumptions: Optional[List[str]] = None):
		# Check values dict first (UI mode)
		if self.values and 'primary_key_cols' in self.values:
			pkey_value = self.values['primary_key_cols']
			# Handle both list and string formats
			if isinstance(pkey_value, list):
				return pkey_value
			return pkey_value.split(',') if pkey_value else []

		# Original CLI behavior
		if self.use_env:
			pkey_str = os.getenv('primary_key_cols', '')
			return pkey_str.split(',') if pkey_str else []
		else:
			# Run loop to get all pkeys
			pkey = []
			while True:
				if not pkey:
					prompt = f"Enter first primary Key column name. Detected possibilities: {pkey_assumptions}\n"
				else:
					prompt = "Enter another Primary Key column for composite key or type 'stop' to finish:\n"
				additional_key = self.get_validated_input(
					prompt,
					valid_options=valid_options,
					case_sensitive=True
				)
				if additional_key.lower() == 'stop':
					break
				pkey.append(additional_key)
			return pkey

	def get_validated_input(
		self,
		prompt: str,
		valid_options: Optional[List[str]] = None,
		allow_empty: bool = False,
		case_sensitive: bool = False,
		strip_input: bool = True
	):
		"""Get user input with validation, looping until valid."""
		while True:
			user_input = input(prompt)

			if strip_input:
				user_input = user_input.strip()
			if not user_input and not allow_empty:
				print("Input cannot be empty. Please try again.")
				continue

			if not user_input and allow_empty:
				return user_input

			if valid_options is None:
				return user_input

			comparison_input = user_input if case_sensitive else user_input.lower()
			comparison_options = valid_options if case_sensitive else   [opt.lower() for opt in valid_options]

			if comparison_input in comparison_options:
				return comparison_input
			else:
				print(f"Invalid input. Please enter one of: {', '.join(valid_options)}")


	def get_yes_no_input(self,prompt: str):
		response = self.get_validated_input(prompt, valid_options=['y', 'n'])
		return response == 'y'
